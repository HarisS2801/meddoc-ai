"""API test: chat returns a clean 503 with Groq metadata when the provider
is unavailable."""


def _upload_doc(client) -> int:
    files = {"file": ("notes.txt", b"Follow-up appointments happen monthly.", "text/plain")}
    resp = client.post("/api/documents/upload", files=files)
    assert resp.status_code == 201
    return resp.json()["id"]


def _assert_groq_unavailable(resp):
    assert resp.status_code == 503
    body = resp.json()
    error = body["error"]
    assert error["code"] == "groq_unavailable"
    assert error["success"] is False
    assert error["provider"] == "groq"
    assert error["generation_status"] == "unavailable"
    assert error["error_code"] == "GROQ_UNAVAILABLE"
    assert error["message"]


def test_chat_returns_503_when_provider_fails(client, monkeypatch):
    def _boom():
        raise RuntimeError("provider down")

    monkeypatch.setattr("app.services.chat_service.build_chat_completer", _boom)
    document_id = _upload_doc(client)

    # The question must ground on the uploaded note ("monthly") so retrieval
    # succeeds; only then is Groq invoked and its failure becomes a 503.
    resp = client.post(
        "/api/chat",
        json={"question": "What happens monthly?", "document_ids": [document_id]},
    )

    _assert_groq_unavailable(resp)


def test_chat_returns_503_when_retrieval_fails(client, monkeypatch):
    def _boom():
        raise RuntimeError("provider down")

    monkeypatch.setattr("app.services.chat_service._retrieve", _boom)
    document_id = _upload_doc(client)

    resp = client.post(
        "/api/chat",
        json={"question": "Where is the clinic?", "document_ids": [document_id]},
    )

    _assert_groq_unavailable(resp)