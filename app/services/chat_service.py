import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from app.config import get_settings
from app.schemas import AnswerType, ChatMessage, ChatResponse, Source
from app.services.llm_service import GENERAL_INSTRUCTION, llm_service
from app.services.rag_service import rag_service
from app.services.session_store import session_store

logger = logging.getLogger(__name__)

STOPPED_NOTE = "\n\n(Response stopped)"


class SessionNotFoundError(LookupError):
    pass


def friendly_error(exc: BaseException) -> str:
    """Turn errors into messages a user can act on. Internal details only go to the logs."""
    if isinstance(exc, asyncio.TimeoutError):
        return "The request took too long. Please try again."
    code = getattr(exc, "code", None)
    if code == 429:
        return "Gemini rate limit reached. Please wait a minute and try again."
    if code == 503:
        return "Gemini is overloaded right now. Please try again in a few seconds."
    return "Something went wrong while generating the answer. Please try again."


class ChatService:
    """Runs one chat turn: load history -> answer -> save both messages."""

    def load_session(self, session_id: str | None, user_id: str) -> tuple[str, list[ChatMessage]]:
        if session_id is None:
            return session_store.create(user_id), []
        messages = session_store.get_messages(session_id, user_id)
        if messages is None:
            raise SessionNotFoundError(session_id)
        return session_id, messages[-get_settings().history_max_messages :]

    def _save(
        self,
        session_id: str,
        user_id: str,
        question: str,
        answer: str,
        answer_type: AnswerType,
        sources: list[Source],
        route_reason: str | None = None,
    ) -> ChatResponse:
        now = datetime.now(timezone.utc)
        session_store.append(
            session_id,
            user_id,
            [
                ChatMessage(role="user", content=question, created_at=now),
                ChatMessage(
                    role="assistant",
                    content=answer,
                    answer_type=answer_type,
                    sources=sources,
                    route_reason=route_reason,
                    created_at=now,
                ),
            ],
        )
        return ChatResponse(
            session_id=session_id,
            answer=answer,
            answer_type=answer_type,
            sources=sources,
            route_reason=route_reason,
        )

    async def ask_general(self, question: str, session_id: str | None, user_id: str) -> ChatResponse:
        session_id, history = self.load_session(session_id, user_id)
        answer = await asyncio.wait_for(
            llm_service.ask(question, system_instruction=GENERAL_INSTRUCTION, history=history),
            timeout=get_settings().request_timeout_seconds,
        )
        return self._save(session_id, user_id, question, answer, "general", [])

    async def ask_documents(
        self, question: str, session_id: str | None, document_id: str | None, user_id: str
    ) -> ChatResponse:
        session_id, history = self.load_session(session_id, user_id)
        answer, answer_type, sources = await asyncio.wait_for(
            rag_service.answer(question, user_id, document_id, history),
            timeout=get_settings().request_timeout_seconds,
        )
        return self._save(session_id, user_id, question, answer, answer_type, sources)

    async def stream(
        self,
        question: str,
        session_id: str,
        history: list[ChatMessage],
        mode: str,
        document_id: str | None,
        user_id: str,
    ) -> AsyncIterator[tuple[str, dict]]:
        """Run the LangGraph workflow and yield (event, data) pairs for SSE:
        meta -> status/route/delta/replace* -> done, or error.

        Graph nodes push events into a queue while the graph runs as a
        background task; this generator forwards them as they arrive.
        If the client disconnects mid-answer, the partial answer is still saved
        (marked as stopped) so the history stays consistent.
        """
        from app.agent.graph import chat_graph  # imported here to avoid a circular import

        yield "meta", {"session_id": session_id, "mode": mode}

        queue: asyncio.Queue[dict] = asyncio.Queue()
        initial_state = {
            "user_id": user_id,
            "question": question,
            "history": history,
            "mode": mode,
            "document_id": document_id,
        }

        async def run_graph() -> None:
            try:
                final = await asyncio.wait_for(
                    chat_graph.ainvoke(
                        initial_state, config={"configurable": {"emit": queue.put_nowait}}
                    ),
                    timeout=get_settings().request_timeout_seconds,
                )
                queue.put_nowait({"type": "_final", "state": final})
            except Exception as exc:
                queue.put_nowait({"type": "_error", "error": exc})

        task = asyncio.create_task(run_graph())
        parts: list[str] = []
        route: dict = {}
        finished = False
        try:
            while True:
                event = await queue.get()
                kind = event.pop("type")
                if kind == "delta":
                    parts.append(event["text"])
                    yield "delta", event
                elif kind == "replace":
                    parts = [event["text"]]
                    yield "replace", event
                elif kind in ("status", "route"):
                    if kind == "route":
                        route = event
                        logger.info("chat_routed", extra={"route": event["route"], "routed_by": event["routed_by"]})
                    yield kind, event
                elif kind == "_error":
                    finished = True  # don't save a failed answer
                    exc = event["error"]
                    logger.error("chat_failed", exc_info=exc, extra={"error_type": type(exc).__name__})
                    yield "error", {"detail": friendly_error(exc)}
                    return
                elif kind == "_final":
                    state = event["state"]
                    response = self._save(
                        session_id,
                        user_id,
                        question,
                        state["answer"],
                        state["answer_type"],
                        state.get("sources", []),
                        state.get("route_reason"),
                    )
                    finished = True
                    logger.info(
                        "chat_completed",
                        extra={"answer_type": state["answer_type"], "sources": len(response.sources)},
                    )
                    yield "done", response.model_dump(mode="json")
                    return
        finally:
            if not task.done():
                task.cancel()  # client disconnected: stop the graph (and Gemini)
            if not finished and parts:
                answer_type: AnswerType = "general" if route.get("route") == "direct" else "document"
                self._save(
                    session_id,
                    user_id,
                    question,
                    "".join(parts) + STOPPED_NOTE,
                    answer_type,
                    [],
                    route.get("reason"),
                )


chat_service = ChatService()
