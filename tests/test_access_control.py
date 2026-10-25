"""Users must never see, search or modify each other's documents or conversations."""

from app.services.session_store import session_store
from app.services.user_store import user_store
from app.services.vector_store import vector_store
from tests.conftest import fake_vector, make_pdf, register, upload


def _user_id(client, headers) -> str:
    return client.get("/api/auth/me", headers=headers).json()["user_id"]


def test_documents_are_private_to_their_owner(client):
    alice, bob = register(client), register(client)
    doc = upload(client, alice, make_pdf("Alice's secret salary is 99000.")).json()
    doc_id = doc["document_id"]

    assert [d["document_id"] for d in client.get("/api/documents", headers=alice).json()] == [doc_id]
    assert client.get("/api/documents", headers=bob).json() == []

    # Every way of reaching Alice's document looks like "not found" to Bob.
    assert client.get(f"/api/documents/{doc_id}", headers=bob).status_code == 404
    assert client.get(f"/api/documents/{doc_id}/text", headers=bob).status_code == 404
    assert client.post(f"/api/documents/{doc_id}/reindex", headers=bob).status_code == 404
    assert client.delete(f"/api/documents/{doc_id}", headers=bob).status_code == 404
    stream = client.post("/api/chat/stream", headers=bob, json={"question": "salary?", "document_id": doc_id})
    assert stream.status_code == 404

    # ...and Alice still has it.
    assert client.get(f"/api/documents/{doc_id}", headers=alice).status_code == 200


def test_vector_search_only_returns_the_callers_chunks(client):
    alice, bob = register(client), register(client)
    upload(client, alice, make_pdf("The launch code for project falcon is 4471."))
    alice_id, bob_id = _user_id(client, alice), _user_id(client, bob)

    query = fake_vector("launch code project falcon")
    assert vector_store.search(query, 5, alice_id), "owner should find their chunk"
    assert vector_store.search(query, 5, bob_id) == []
    assert vector_store.has_documents(alice_id) and not vector_store.has_documents(bob_id)


def test_sessions_are_private_to_their_owner(client):
    alice, bob = register(client), register(client)
    session_id = session_store.create(_user_id(client, alice))

    assert client.get(f"/api/chat/sessions/{session_id}", headers=alice).status_code == 200
    assert client.get(f"/api/chat/sessions/{session_id}", headers=bob).status_code == 404
    assert client.delete(f"/api/chat/sessions/{session_id}", headers=bob).status_code == 404
    stream = client.post("/api/chat/stream", headers=bob, json={"question": "hi", "session_id": session_id})
    assert stream.status_code == 404


def test_deleting_a_document_removes_its_vectors(client):
    alice = register(client)
    doc_id = upload(client, alice, make_pdf("Quarterly revenue grew by 12 percent.")).json()["document_id"]
    alice_id = _user_id(client, alice)

    assert client.delete(f"/api/documents/{doc_id}", headers=alice).status_code == 204
    assert not vector_store.has_documents(alice_id)
    assert user_store.get(alice_id) is not None
