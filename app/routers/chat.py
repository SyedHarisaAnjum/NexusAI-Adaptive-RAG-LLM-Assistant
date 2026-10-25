import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.auth.dependencies import ChatUser, CurrentUser
from app.schemas import (
    AskRequest,
    ChatResponse,
    DocumentAskRequest,
    SessionHistory,
    StreamRequest,
)
from app.services.chat_service import SessionNotFoundError, chat_service, friendly_error
from app.services.document_store import document_store
from app.services.session_store import session_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

SESSION_NOT_FOUND = "Session not found. Omit session_id to start a new conversation."


async def _to_sse(events: AsyncIterator[tuple[str, dict]]) -> AsyncIterator[str]:
    """Format (event, data) pairs as Server-Sent Events."""
    async for event, data in events:
        yield f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _check_document(document_id: str | None, user_id: str) -> None:
    if document_id and document_store.get(document_id, user_id) is None:
        raise HTTPException(status_code=404, detail="Document not found.")


@router.post("/stream")
async def stream(request: StreamRequest, user: ChatUser) -> StreamingResponse:
    """Stream the answer as Server-Sent Events.

    The request runs through the LangGraph workflow (app/agent/graph.py), which
    decides between a direct Gemini answer and RAG.

    Events: `meta` {session_id, mode} -> `status` {text} / `route` {route, routed_by, reason}
    / `delta` {text} / `replace` {text} (any order, repeated) ->
    `done` {session_id, answer, answer_type, sources, route_reason}, or `error` {detail}.
    """
    # Validate before streaming starts, so these still return proper HTTP status codes.
    if request.mode != "general":
        _check_document(request.document_id, user.user_id)
    try:
        session_id, history = chat_service.load_session(request.session_id, user.user_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND)

    events = chat_service.stream(
        request.question, session_id, history, request.mode, request.document_id, user.user_id
    )
    return StreamingResponse(
        _to_sse(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/ask", response_model=ChatResponse)
async def ask(request: AskRequest, user: ChatUser) -> ChatResponse:
    """General Gemini answer (does not use uploaded documents)."""
    try:
        return await chat_service.ask_general(request.question, request.session_id, user.user_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND)
    except Exception as exc:
        logger.error("chat_failed", exc_info=exc)
        raise HTTPException(status_code=502, detail=friendly_error(exc))


@router.post("/ask-documents", response_model=ChatResponse)
async def ask_documents(request: DocumentAskRequest, user: ChatUser) -> ChatResponse:
    """Document-grounded answer with sources (RAG)."""
    _check_document(request.document_id, user.user_id)
    try:
        return await chat_service.ask_documents(
            request.question, request.session_id, request.document_id, user.user_id
        )
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND)
    except Exception as exc:
        logger.error("chat_failed", exc_info=exc)
        raise HTTPException(status_code=502, detail=friendly_error(exc))


@router.get("/sessions/{session_id}", response_model=SessionHistory)
async def get_session(session_id: str, user: CurrentUser) -> SessionHistory:
    messages = session_store.get_messages(session_id, user.user_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return SessionHistory(session_id=session_id, messages=messages)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, user: CurrentUser) -> None:
    if not session_store.delete(session_id, user.user_id):
        raise HTTPException(status_code=404, detail="Session not found.")
