from app.config import get_settings
from tests.conftest import make_pdf, register, upload


def test_login_is_rate_limited_per_ip(client):
    limit = get_settings().rate_limit_auth_per_minute
    for _ in range(limit):
        client.post("/api/auth/login", data={"username": "x@example.com", "password": "wrong-pass"})
    response = client.post("/api/auth/login", data={"username": "x@example.com", "password": "wrong-pass"})
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0


def test_chat_is_rate_limited_per_user(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_chat_per_minute", 2)
    user = register(client)
    # A session id that doesn't exist fails fast with 404 - after the rate limit check.
    body = {"question": "hi", "session_id": "0" * 32}
    assert client.post("/api/chat/stream", headers=user, json=body).status_code == 404
    assert client.post("/api/chat/stream", headers=user, json=body).status_code == 404
    assert client.post("/api/chat/stream", headers=user, json=body).status_code == 429


def test_oversized_upload_rejected_before_reading_body(client):
    user = register(client)
    too_big = b"%PDF-" + b"0" * ((get_settings().max_upload_mb + 2) * 1024 * 1024)
    response = upload(client, user, too_big)
    assert response.status_code == 413


def test_upload_content_is_validated(client):
    user = register(client)
    assert upload(client, user, b"just text pretending", name="fake.pdf").status_code == 400
    assert upload(client, user, make_pdf("hello"), name="notes.txt").status_code == 400
    assert upload(client, user, b"", name="empty.pdf").status_code in (400, 411)


def test_per_user_document_quota(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_documents_per_user", 1)
    user = register(client)
    assert upload(client, user, make_pdf("first document")).status_code == 201
    assert upload(client, user, make_pdf("second document")).status_code == 403


def test_responses_carry_request_id_and_security_headers(client):
    response = client.get("/health", headers={"X-Request-ID": "trace-123"})
    assert response.headers["X-Request-ID"] == "trace-123"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
