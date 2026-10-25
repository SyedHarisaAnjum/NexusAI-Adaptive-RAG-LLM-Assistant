"""Agent routing with Gemini stubbed out (the classifier LLM is disabled in conftest)."""

import asyncio

import pytest

from app.agent import nodes
from app.agent.graph import chat_graph
from tests.conftest import make_pdf, register, upload


@pytest.fixture(autouse=True)
def fake_gemini(monkeypatch):
    async def general_stream(question, *args, **kwargs):
        yield "general answer"

    def grounded_stream(plan):
        async def gen():
            yield "From the document [1]."
        return gen()

    monkeypatch.setattr(nodes.llm_service, "ask_stream", general_stream)
    monkeypatch.setattr(nodes.rag_service, "stream", grounded_stream)


def _run(user_id: str, question: str, mode: str = "auto") -> dict:
    state = {"user_id": user_id, "question": question, "history": [], "mode": mode, "document_id": None}
    return asyncio.run(chat_graph.ainvoke(state, config={"configurable": {"emit": lambda e: None}}))


def _user_id(client, headers) -> str:
    return client.get("/api/auth/me", headers=headers).json()["user_id"]


def test_user_without_documents_gets_a_direct_answer(client):
    user_id = _user_id(client, register(client))
    result = _run(user_id, "What is the capital of France?")
    assert result["route"] == "direct" and result["answer_type"] == "general"


def test_question_about_the_documents_uses_rag_with_sources(client):
    headers = register(client)
    upload(client, headers, make_pdf("Employees receive 27 days of paid annual leave."), name="handbook.pdf")
    result = _run(_user_id(client, headers), "What does the document say about paid annual leave?")
    assert result["route"] == "rag" and result["routed_by"] == "rule"
    assert result["answer_type"] == "document"
    assert result["sources"][0].filename == "handbook.pdf"


def test_general_mode_never_touches_documents(client):
    headers = register(client)
    upload(client, headers, make_pdf("Employees receive 27 days of paid annual leave."))
    result = _run(_user_id(client, headers), "paid annual leave?", mode="general")
    assert result["route"] == "direct" and result["routed_by"] == "user"


def test_other_users_documents_do_not_affect_routing(client):
    owner = register(client)
    upload(client, owner, make_pdf("Employees receive 27 days of paid annual leave."))
    stranger_id = _user_id(client, register(client))
    result = _run(stranger_id, "What does the document say about paid annual leave?")
    assert result["route"] == "direct"  # the stranger has no documents of their own
