import logging
import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import Literal

from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.agent.state import Route, RoutedBy
from app.config import get_settings
from app.schemas import ChatMessage
from app.services.document_store import document_store
from app.services.llm_service import llm_service
from app.services.prompt_safety import sanitize_attribute
from app.services.vector_store import vector_store

logger = logging.getLogger(__name__)

# Phrases that clearly point at the user's uploaded files.
DOCUMENT_HINTS = re.compile(
    r"\b(documents?|pdfs?|files?|uploaded|attachments?|page\s+\d+|according to the"
    r"|in the (doc|document|pdf|file|text))\b",
    re.IGNORECASE,
)

CLASSIFIER_PROMPT = """You route questions for an assistant that can answer either from the user's uploaded documents or from general knowledge.

Uploaded documents: {filenames}

Recent conversation:
{history}

Question: {question}

Answer "document" if the question is probably answered by the uploaded documents: it asks about their content, about an organisation, policy, product, person or topic those documents would describe, or follows up on an earlier answer that came from the documents.
Answer "general" for general knowledge, definitions, coding, maths, small talk, or anything the documents would not cover."""


class IntentResult(BaseModel):
    intent: Literal["document", "general"]
    reason: str = Field(description="One short sentence explaining the choice, addressed to the user.")


@dataclass
class RouteDecision:
    route: Route
    routed_by: RoutedBy
    reason: str


def _format_history(history: list[ChatMessage]) -> str:
    recent = history[-4:]
    if not recent:
        return "(none)"
    return "\n".join(f"{m.role}: {m.content[:200]}" for m in recent)


def _normalise(name: str) -> str:
    return re.sub(r"[_\-.]+", " ", name).strip().lower()


async def classify(
    question: str,
    history: list[ChatMessage],
    mode: str,
    document_id: str | None,
    user_id: str,
) -> RouteDecision:
    """Decide between a direct Gemini answer and RAG.

    Cheap, predictable rules run first; the LLM classifier is only used when
    the rules can't tell.
    """
    # 1. The user chose explicitly.
    if mode == "general":
        return RouteDecision("direct", "user", "You chose General mode.")
    if mode == "documents":
        return RouteDecision("rag", "user", "You chose Documents mode.")

    # 2. Rules.
    if document_id:
        return RouteDecision("rag", "rule", "A specific document is selected.")

    documents = document_store.list_documents(user_id)
    if not documents or not await run_in_threadpool(vector_store.has_documents, user_id):
        return RouteDecision("direct", "rule", "No documents are uploaded, so I used general knowledge.")

    if DOCUMENT_HINTS.search(question):
        return RouteDecision("rag", "rule", "Your question refers to your documents.")

    lowered = _normalise(question)
    for doc in documents:
        stem = _normalise(PurePath(doc.filename).stem)
        if len(stem) >= 4 and stem in lowered:
            return RouteDecision("rag", "rule", f"Your question mentions {doc.filename}.")

    # 3. LLM intent classifier.
    settings = get_settings()
    if settings.router_use_llm:
        prompt = CLASSIFIER_PROMPT.format(
            # Filenames are user-controlled, so strip anything that could act as markup.
            filenames=", ".join(sanitize_attribute(d.filename) for d in documents),
            history=_format_history(history),
            question=question,
        )
        try:
            result = await llm_service.ask_json(prompt, IntentResult, model=settings.router_model)
            route: Route = "rag" if result.intent == "document" else "direct"
            return RouteDecision(route, "llm", result.reason)
        except Exception as exc:
            # Rate limits etc. shouldn't break the chat - fall through to the default.
            logger.warning("Intent classifier failed, using default route: %s", exc)

    # 4. Default: try the documents; weak retrieval then falls back to a direct answer.
    return RouteDecision("rag", "default", "Checking your documents first.")
