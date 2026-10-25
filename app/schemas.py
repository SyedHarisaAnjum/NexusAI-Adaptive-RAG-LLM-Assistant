from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# "general"   -> answered from Gemini's own knowledge (no documents used)
# "document"  -> grounded in uploaded documents, with sources
# "not_found" -> document mode, but nothing relevant was found
AnswerType = Literal["general", "document", "not_found"]


class AskRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        examples=["What is machine learning?"],
    )
    # Omit to start a new conversation; send the returned id for follow-ups.
    session_id: str | None = None


class DocumentAskRequest(AskRequest):
    # Omit to search across all uploaded documents.
    document_id: str | None = None


class StreamRequest(DocumentAskRequest):
    # "auto"      -> the agent decides per question (documents or general)
    # "documents" -> always a grounded answer with sources
    # "general"   -> always plain Gemini
    mode: Literal["auto", "documents", "general"] = "auto"


class Source(BaseModel):
    ref: int  # matches the [n] citation marker in the answer
    document_id: str
    filename: str
    page_number: int
    score: float
    excerpt: str


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    answer_type: AnswerType
    sources: list[Source] = []
    # Why the agent chose this path, e.g. "The question refers to your documents."
    route_reason: str | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    answer_type: AnswerType | None = None
    sources: list[Source] = []
    route_reason: str | None = None
    created_at: datetime


class SessionHistory(BaseModel):
    session_id: str
    messages: list[ChatMessage]


class RegisterRequest(BaseModel):
    email: str = Field(
        ...,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        examples=["you@example.com"],
    )
    password: str = Field(..., min_length=8, max_length=128)


class UserPublic(BaseModel):
    user_id: str
    email: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic


class DocumentMetadata(BaseModel):
    document_id: str
    owner_id: str | None = None
    filename: str
    page_count: int
    size_bytes: int
    char_count: int
    chunk_count: int = 0
    uploaded_at: datetime


class PageText(BaseModel):
    page_number: int
    text: str


class DocumentText(BaseModel):
    document_id: str
    pages: list[PageText]
