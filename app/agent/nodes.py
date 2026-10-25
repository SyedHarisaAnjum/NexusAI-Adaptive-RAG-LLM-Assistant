"""Graph nodes. Each node receives the current state and returns the keys it changes.

Nodes report progress through an `emit` callback passed in the graph config
(config["configurable"]["emit"]). LangGraph's built-in stream writer can't be
used from async nodes on Python < 3.11, so we pass our own.
"""

from collections.abc import AsyncIterator, Callable

from langchain_core.runnables import RunnableConfig

from app.agent.classifier import classify
from app.agent.state import ChatState
from app.services.llm_service import GENERAL_INSTRUCTION, llm_service
from app.services.rag_service import CLARIFY_HINT, NOT_FOUND_ANSWER, rag_service

Emit = Callable[[dict], None]


def _emitter(config: RunnableConfig) -> Emit:
    return config.get("configurable", {}).get("emit") or (lambda event: None)


async def _stream_text(chunks: AsyncIterator[str], emit: Emit) -> str:
    parts: list[str] = []
    async for text in chunks:
        parts.append(text)
        emit({"type": "delta", "text": text})
    return "".join(parts)


async def classify_question(state: ChatState, config: RunnableConfig) -> dict:
    emit = _emitter(config)
    emit({"type": "status", "text": "Understanding your question…"})
    decision = await classify(
        state["question"],
        state.get("history", []),
        state["mode"],
        state.get("document_id"),
        state["user_id"],
    )
    emit({"type": "route", "route": decision.route, "routed_by": decision.routed_by, "reason": decision.reason})
    return {
        "route": decision.route,
        "routed_by": decision.routed_by,
        "route_reason": decision.reason,
    }


async def direct_answer(state: ChatState, config: RunnableConfig) -> dict:
    emit = _emitter(config)
    update: dict = {}
    if "plan" in state:
        # We got here because retrieval found nothing relevant (see route_after_retrieval).
        reason = "Nothing relevant was found in your documents, so I used general knowledge."
        update = {"route": "direct", "route_reason": reason}
        emit({"type": "route", "route": "direct", "routed_by": "default", "reason": reason})

    emit({"type": "status", "text": "Answering from general knowledge…"})
    answer = await _stream_text(
        llm_service.ask_stream(state["question"], GENERAL_INSTRUCTION, state.get("history")),
        emit,
    )
    return {**update, "answer": answer, "answer_type": "general", "sources": []}


async def retrieve_documents(state: ChatState, config: RunnableConfig) -> dict:
    _emitter(config)({"type": "status", "text": "Searching your documents…"})
    plan = await rag_service.plan(
        state["question"], state["user_id"], state.get("document_id"), state.get("history")
    )
    return {"plan": plan}


async def generate_grounded_answer(state: ChatState, config: RunnableConfig) -> dict:
    emit = _emitter(config)
    emit({"type": "status", "text": "Writing an answer from your documents…"})
    answer = await _stream_text(rag_service.stream(state["plan"]), emit)
    return {"answer": answer}


async def validate_answer(state: ChatState) -> dict:
    failure, sources = rag_service.validate(state["answer"], state["plan"])
    if failure:
        return {"validation_error": failure}
    return {"validation_error": None, "answer_type": "document", "sources": sources}


async def fallback_response(state: ChatState, config: RunnableConfig) -> dict:
    plan = state.get("plan")
    if plan is not None and plan.fallback and plan.fallback != NOT_FOUND_ANSWER:
        message = plan.fallback  # e.g. "No documents have been uploaded yet…"
    else:
        message = f"{NOT_FOUND_ANSWER} {CLARIFY_HINT}"
    # "replace" (not "delta"): a rejected grounded answer may already be on screen.
    _emitter(config)({"type": "replace", "text": message})
    return {"answer": message, "answer_type": "not_found", "sources": []}
