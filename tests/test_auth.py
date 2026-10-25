from tests.conftest import register


def test_register_login_and_me(client):
    response = client.post(
        "/api/auth/register", json={"email": "Alice@Example.com", "password": "s3cure-password"}
    )
    assert response.status_code == 201
    assert response.json()["user"]["email"] == "alice@example.com"  # normalised

    login = client.post(
        "/api/auth/login", data={"username": "alice@example.com", "password": "s3cure-password"}
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"
    assert "password_hash" not in me.json()


def test_duplicate_email_rejected(client):
    register(client, "dup@example.com")
    response = client.post(
        "/api/auth/register", json={"email": "DUP@example.com", "password": "another-password"}
    )
    assert response.status_code == 409


def test_wrong_password_and_unknown_email_look_identical(client):
    register(client, "bob@example.com", "right-password")
    wrong = client.post("/api/auth/login", data={"username": "bob@example.com", "password": "nope-nope"})
    unknown = client.post("/api/auth/login", data={"username": "nobody@example.com", "password": "nope-nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_weak_password_and_bad_email_rejected(client):
    assert client.post("/api/auth/register", json={"email": "x@example.com", "password": "short"}).status_code == 422
    assert client.post("/api/auth/register", json={"email": "not-an-email", "password": "long-enough-pw"}).status_code == 422


def test_protected_endpoints_require_a_valid_token(client):
    assert client.get("/api/documents").status_code == 401
    assert client.post("/api/chat/stream", json={"question": "hi"}).status_code == 401
    bad = {"Authorization": "Bearer not.a.real.token"}
    assert client.get("/api/documents", headers=bad).status_code == 401


def test_health_is_public(client):
    assert client.get("/health").json()["status"] == "ok"
