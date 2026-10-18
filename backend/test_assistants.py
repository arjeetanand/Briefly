import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app
from routes import assistants


@pytest.fixture
def clients(tmp_path, monkeypatch):
    monkeypatch.setattr(assistants, "DATABASE_PATH", tmp_path / "pilot.sqlite3")
    monkeypatch.setenv("PITCHROOM_ACCESS_TOKEN", "pilot-invite")
    monkeypatch.setenv("RETRIEVAL_PROVIDER", "lexical")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    first = TestClient(app.app, base_url="http://localhost")
    second = TestClient(app.app, base_url="http://localhost")
    for client, email in ((first, "first@example.com"), (second, "second@example.com")):
        response = client.post("/api/auth/register", json={
            "email": email, "password": "a-unique-pilot-password", "invite_code": "pilot-invite",
        })
        assert response.status_code == 200
    yield first, second


def test_private_assistants_approve_sources_and_isolate_owners(clients):
    first, second = clients
    assistant = first.post("/api/assistants", json={"name": "Customer guide"}).json()
    forbidden = second.get(f"/api/assistants/{assistant['id']}")
    assert forbidden.status_code == 404

    upload = first.post(f"/api/assistants/{assistant['id']}/sources/files", files={
        "file": ("faq.txt", b"Customers can request a refund within 30 days.", "text/plain"),
    })
    assert upload.status_code == 200
    assert upload.json()["approved"] is False
    blocked_until_approval = first.post(f"/api/assistants/{assistant['id']}/answer", json={
        "question": "How long do customers have to request a refund?",
    })
    assert blocked_until_approval.status_code == 409

    source = first.get(f"/api/assistants/{assistant['id']}").json()["sources"][0]
    assert source["metadata"]["imported_at"]
    assert first.patch(f"/api/assistants/{assistant['id']}/sources/{source['id']}", json={"approved": True}).status_code == 200
    answer = first.post(f"/api/assistants/{assistant['id']}/answer", json={
        "question": "How long do customers have to request a refund?",
    }).json()
    assert answer["grounded"] is True
    assert "30 days" in answer["answer"]
    assert answer["source_refs"][0]["citation"]
    standalone_this = first.post(f"/api/assistants/{assistant['id']}/answer", json={
        "question": "What is this refund policy?",
    }).json()
    assert standalone_this["grounded"] is True
    assert "30 days" in standalone_this["answer"]
    follow_up = first.post(f"/api/assistants/{assistant['id']}/answer", json={
        "question": "How many days is that?",
        "history": [
            {"role": "user", "content": "How long do customers have to request a refund?"},
            {"role": "assistant", "content": answer["answer"]},
        ],
    }).json()
    assert follow_up["grounded"] is True
    assert "30 days" in follow_up["answer"]
    unsupported_follow_up = first.post(f"/api/assistants/{assistant['id']}/answer", json={
        "question": "Does that include gift orders?",
        "history": [
            {"role": "user", "content": "How long do customers have to request a refund?"},
            {"role": "assistant", "content": answer["answer"]},
        ],
    }).json()
    assert unsupported_follow_up["grounded"] is False

    wrong_owner = second.post(f"/api/assistants/{assistant['id']}/answer", json={"question": "What is the refund policy?"})
    assert wrong_owner.status_code == 404


def test_deleting_assistant_removes_its_sources_and_public_link(clients):
    first, _ = clients
    assistant = first.post("/api/assistants", json={"name": "Temporary guide"}).json()
    path = f"/api/assistants/{assistant['id']}"
    first.post(f"{path}/sources/files", files={"file": ("guide.txt", b"Office hours are every Friday.", "text/plain")})
    source = first.get(path).json()["sources"][0]
    first.patch(f"{path}/sources/{source['id']}", json={"approved": True})
    token = first.post(f"{path}/publish").json()["url"].split("/")[-1]

    deleted = first.delete(path)
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}
    assert first.get(path).status_code == 404
    assert first.get(f"/api/shared/{token}").status_code == 404


def test_publish_is_an_immutable_snapshot_and_can_be_revoked(clients):
    first, _ = clients
    assistant = first.post("/api/assistants", json={"name": "Returns"}).json()
    path = f"/api/assistants/{assistant['id']}"
    first.post(f"{path}/sources/files", files={"file": ("faq.txt", b"Customers can request a refund within 30 days.", "text/plain")})
    source = first.get(path).json()["sources"][0]
    first.patch(f"{path}/sources/{source['id']}", json={"approved": True})
    published = first.post(f"{path}/publish").json()
    token = published["url"].split("/")[-1]

    replacement = first.post(f"{path}/sources/files", files={"file": ("faq.txt", b"Customers can request a refund within 60 days.", "text/plain")})
    assert replacement.json()["status"] == "updated"
    current = first.get(path).json()
    assert current["published_stale"] is True
    assert current["sources"][0]["approved"] is False
    first.patch(f"{path}/sources/{source['id']}", json={"approved": True})

    old_link_answer = first.post(f"/api/shared/{token}/answer", json={
        "question": "How long do customers have to request a refund?",
    }).json()
    assert "30 days" in old_link_answer["answer"]
    first.post(f"/api/shared/{token}/feedback", json={"answer_id": old_link_answer["answer_id"], "rating": 1})
    metrics = first.get(f"{path}/metrics").json()
    assert metrics["helpful"] == 1

    first.delete(f"{path}/publish")
    assert first.get(f"/api/shared/{token}").status_code == 404


def test_metrics_estimate_embedding_cost_per_conversation_session(clients, monkeypatch):
    first, _ = clients
    assistant = first.post("/api/assistants", json={"name": "Returns"}).json()
    path = f"/api/assistants/{assistant['id']}"
    first.post(f"{path}/sources/files", files={"file": ("faq.txt", b"Refunds are accepted within 30 days.", "text/plain")})
    source = first.get(path).json()["sources"][0]
    first.patch(f"{path}/sources/{source['id']}", json={"approved": True})
    monkeypatch.setattr(assistants, "_semantic_scores", lambda db, question, sections: ({}, 100))

    answers = []
    for session_id in ("session-a", "session-a", "session-b"):
        answer = first.post(f"{path}/answer", json={
            "question": "How many days are refunds accepted?", "session_id": session_id,
        }).json()
        assert answer["estimated_cost_usd"] == pytest.approx(0.000002)
        answers.append(answer)
    first.post(f"{path}/feedback", json={"answer_id": answers[0]["answer_id"], "rating": 1})
    first.post(f"{path}/feedback", json={"answer_id": answers[1]["answer_id"], "rating": -1})
    metrics = first.get(f"{path}/metrics").json()
    assert metrics["sessions"] == 2
    assert metrics["embedding_tokens"] == 300
    assert metrics["avg_embedding_cost_per_session_usd"] == pytest.approx(0.000003)
    assert metrics["helpful"] == metrics["not_helpful"] == 1


def test_assistant_question_quota_applies_to_private_and_shared_answers(clients, monkeypatch):
    first, _ = clients
    assistant = first.post("/api/assistants", json={"name": "Returns"}).json()
    path = f"/api/assistants/{assistant['id']}"
    first.post(f"{path}/sources/files", files={"file": ("faq.txt", b"Refunds are accepted within 30 days.", "text/plain")})
    source = first.get(path).json()["sources"][0]
    first.patch(f"{path}/sources/{source['id']}", json={"approved": True})
    share = first.post(f"{path}/publish").json()
    token = share["url"].split("/")[-1]
    monkeypatch.setattr(assistants, "MAX_ASSISTANT_ANSWERS_PER_MINUTE", 1)
    question = {"question": "How many days are refunds accepted?"}
    assert first.post(f"{path}/answer", json=question).status_code == 200
    assert first.post(f"{path}/answer", json=question).status_code == 429
    assert first.post(f"/api/shared/{token}/answer", json=question).status_code == 429


def test_invite_code_and_public_url_network_boundary(clients, monkeypatch):
    first, _ = clients
    rejected = first.post("/api/auth/register", json={
        "email": "not-invited@example.com", "password": "a-unique-pilot-password", "invite_code": "wrong",
    })
    assert rejected.status_code == 403
    with pytest.raises(HTTPException):
        assistants._safe_public_url("http://127.0.0.1/robots.txt")

    monkeypatch.setattr(assistants.socket, "getaddrinfo", lambda *args, **kwargs: [
        (2, 1, 6, "", ("203.0.113.10", args[1])),
    ])
    with pytest.raises(HTTPException):
        assistants._safe_public_url("https://docs.example.com/private")


def test_website_import_respects_robots_and_keeps_page_citations(monkeypatch):
    monkeypatch.setattr(assistants.socket, "getaddrinfo", lambda *args, **kwargs: [
        (2, 1, 6, "", ("8.8.8.8", args[1])),
    ])
    def fetch(url, host, limit, **kwargs):
        if url.endswith("robots.txt"):
            body = b"User-agent: *\nDisallow: /private\nSitemap: https://docs.example.com/sitemap.xml"
            return 200, {"content-type": "text/plain"}, body, url
        if url.endswith("sitemap.xml"):
            body = b"<urlset><url><loc>https://docs.example.com/</loc></url><url><loc>https://docs.example.com/about</loc></url><url><loc>https://docs.example.com/private</loc></url></urlset>"
            return 200, {"content-type": "application/xml"}, body, url
        title = "Home" if url.endswith("/") else "About"
        text = "Our support team answers product questions." if title == "Home" else "Shipping is free for every order."
        body = f"<html><title>{title}</title><h1>{title}</h1><p>{text}</p><script>ignore this text</script></html>".encode()
        return 200, {"content-type": "text/html; charset=utf-8"}, body, url
    monkeypatch.setattr(assistants, "_safe_get", fetch)
    result = assistants._crawl_site("https://docs.example.com/")
    assert len(result["sources"]) == 2
    assert result["skipped"] == 1
    assert "https://docs.example.com/private" in result["skipped_pages"]
    assert all(section.url == source["url"] for source in result["sources"] for section in source["sections"])
    assert all("ignore this text" not in section.text for source in result["sources"] for section in source["sections"])


def test_semantic_retrieval_caches_source_embeddings(tmp_path, monkeypatch):
    monkeypatch.setattr(assistants, "DATABASE_PATH", tmp_path / "embeddings.sqlite3")
    monkeypatch.setenv("RETRIEVAL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = []
    def embed(texts):
        calls.append(texts)
        vectors = [[1.0, 0.0] if "parental leave" in text.lower() or "time off" in text.lower() else [0.0, 1.0] for text in texts]
        return vectors, 5
    monkeypatch.setattr(assistants, "_embed", embed)
    section = assistants.SourceSection("Employees receive 16 weeks of parental leave.", "HR guide · 1")
    with assistants._connect() as db:
        scores, tokens = assistants._semantic_scores(db, "How much time off do parents receive?", [section])
        assert scores[0] == pytest.approx(1.0)
        assert tokens == 10
        scores, tokens = assistants._semantic_scores(db, "How much time off do parents receive?", [section])
        assert scores[0] == pytest.approx(1.0)
        assert tokens == 5
    assert len(calls) == 3
