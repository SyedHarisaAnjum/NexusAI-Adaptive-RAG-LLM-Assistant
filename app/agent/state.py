from typing import Literal, TypedDict

from app.schemas import AnswerType, ChatMessage, Source
from app.services.rag_service import RAGPlan

Route = Literal["direct", "rag"]
# Who made the routing decision: the user's mode toggle, a fixed rule,
# the LLM classifier, or a default guess when nothing else applied.
RoutedBy = Literal["user", "rule", "llm", "default"]


class ChatState(TypedDict, total=False):
    """Data passed between graph nodes. Each node returns the keys it updates."""

    # Inputs
    user_id: str  # every document lookup is restricted to this user's files
    question: str
    history: list[ChatMessage]
    mode: Literal["auto", "documents", "general"]
    document_id: str | None

    # Set by classify_question
    route: Route
    routed_by: RoutedBy
    route_reason: str

    # Set by retrieve_documents / validate_answer
    plan: RAGPlan
    validation_error: str | None

    # Final output
    answer: str
    answer_type: AnswerType
    sources: list[Source]
