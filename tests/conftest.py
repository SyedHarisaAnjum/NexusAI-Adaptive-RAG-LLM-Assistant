"""Test setup: isolated data directory, fake embeddings, no real Gemini calls.

Environment variables must be set before `app` is imported, because settings
and the stores are created at import time.
"""

import hashlib
import math
import os
import re
import tempfile
import uuid

_tmp = tempfile.mkdtemp(prefix="qa-tests-")
os.environ.update(
    {
        "ENVIRONMENT": "development",
        "DATA_DIR": f"{_tmp}/data",
        "BACKUP_DIR": f"{_tmp}/backups",
        "GEMINI_API_KEY": "test-key-not-real",
        "JWT_SECRET": "test-secret-" + "x" * 40,
        "LOG_JSON": "false",
        "LOG_LEVEL": "WARNING",
        "ROUTER_USE_LLM": "false",
        "RAG_MIN_SCORE": "0.1",
    }
)

import pymupdf  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def fake_vector(text: str, dim: int = 768) -> list[float]:
    """Deterministic bag-of-words embedding: texts sharing words get similar vectors."""
    vec = [0.0] * dim
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch):
    from app.services.embedding_service import embedding_service

    async def embed_documents(texts):
        return [fake_vector(t) for t in texts]

    async def embed_query(text):
        return fake_vector(text)

    monkeypatch.setattr(embedding_service, "embed_documents", embed_documents)
    monkeypatch.setattr(embedding_service, "embed_query", embed_query)


@pytest.fixture(autouse=True)
def reset_rate_limits():
    from app.services.rate_limiter import rate_limiter

    rate_limiter.reset()
    yield
    rate_limiter.reset()


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def register(client, email: str | None = None, password: str = "correct-horse-battery") -> dict:
    """Create a user and return Authorization headers for them."""
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    response = client.post("/api/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def make_pdf(*pages: str) -> bytes:
    doc = pymupdf.open()
    for text in pages:
        doc.new_page().insert_textbox(pymupdf.Rect(72, 72, 520, 760), text)
    return doc.tobytes()


def upload(client, headers: dict, pdf: bytes, name: str = "notes.pdf"):
    return client.post(
        "/api/documents/upload",
        headers=headers,
        files={"file": (name, pdf, "application/pdf")},
    )
