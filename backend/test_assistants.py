import shutil

import pymupdf
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app
from routes import assistants, pitch as pitch_routes


@pytest.fixture
def clients(tmp_path, monkeypatch):
    monkeypatch.setattr(assistants, "DATABASE_PATH", tmp_path / "pilot.sqlite3")
    monkeypatch.setenv("PITCHROOM_ACCESS_TOKEN", "pilot-invite")
    monkeypatch.setenv("RETRIEVAL_PROVIDER", "lexical")
    monkeypatch.setenv("ANSWER_GENERATION_PROVIDER", "extractive")
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
            {"role": "assistant", "content": answer["spoken_answer"]},
        ],
    }).json()
    assert follow_up["grounded"] is True
    assert "30 days" in follow_up["answer"]
    unsupported_follow_up = first.post(f"/api/assistants/{assistant['id']}/answer", json={
        "question": "Does that include gift orders?",
        "history": [
            {"role": "user", "content": "How long do customers have to request a refund?"},
            {"role": "assistant", "content": answer["spoken_answer"]},
        ],
    }).json()
    assert unsupported_follow_up["grounded"] is False
    assert unsupported_follow_up["answer"] == unsupported_follow_up["spoken_answer"]
    assert unsupported_follow_up["source_refs"] == []

    wrong_owner = second.post(f"/api/assistants/{assistant['id']}/answer", json={"question": "What is the refund policy?"})
    assert wrong_owner.status_code == 404


def test_starter_deck_enters_private_assistant_unapproved(clients):
    first, _ = clients
    assistant = first.post("/api/assistants", json={"name": "Team handbook"}).json()
    sample = next(item for item in first.get("/api/pitch/samples").json() if item["id"] == "team-handbook")
    download = first.get(sample["download_url"])
    assert download.status_code == 200

    upload = first.post(f"/api/assistants/{assistant['id']}/sources/files", files={
        "file": (
            f"Sample - {sample['filename']}",
            download.content,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
    })
    assert upload.status_code == 200
    assert upload.json()["approved"] is False
    assert first.get(f"/api/assistants/{assistant['id']}").json()["sources"][0]["approved"] is False
    assert first.post(f"/api/assistants/{assistant['id']}/answer", json={
        "question": "How do I get an expense approved?",
    }).status_code == 409


def test_starter_library_is_public_read_only(clients):
    guest = TestClient(app.app, base_url="http://localhost")
    samples = guest.get("/api/pitch/samples")
    assert samples.status_code == 200
    templates = guest.get("/api/pitch/assistant-templates").json()
    assert len(templates) == 5
    for template in templates:
        detail = guest.get(f"/api/pitch/sample-assistants/{template['id']}")
        assert detail.status_code == 200
        assert detail.json()["sources"]
    for sample in samples.json():
        download = guest.get(sample["download_url"])
        assert download.status_code == 200
        assert download.headers["content-type"].startswith(sample["content_type"])
    markdown_demo = TestClient(
        app.app,
        base_url="http://localhost",
        headers={"Authorization": "Bearer pilot-invite"},
    ).post("/api/pitch/sample/course-lessons")
    assert markdown_demo.status_code == 200
    assert markdown_demo.json()["metadata"]["format"] == "markdown"
    assert guest.post("/api/pitch/sample/team-handbook").status_code == 401
    assert guest.post("/api/assistants/from-sample/team-onboarding").status_code == 401
    assert guest.post("/api/voice/answer", json={"question": "What is in the room-wide document?"}).status_code == 401


def test_public_sample_assistants_answer_from_isolated_snapshots_and_limit_speech(clients, monkeypatch):
    guest = TestClient(app.app, base_url="http://localhost")
    examples = {
        "team-onboarding": ("How do I request system access?", "new-starter-guide.pptx · Slide 4"),
        "project-delivery": ("What is blocking the launch?", "weekly-project-update.pptx · Slide 4"),
        "customer-kickoff": ("Who sends the weekly recap?", "customer-success-plan.pptx · Slide 5"),
        "course-companion": ("What are the three steps in Lesson 3?", "course-lesson-guide.md · Source section"),
        "consulting-services": ("How many interviews are included in the sprint?", "consulting-service-guide.md · Source section"),
    }
    answers = {}
    for assistant_id, (question, citation) in examples.items():
        response = guest.post(f"/api/pitch/sample-assistants/{assistant_id}/answer", json={"question": question})
        assert response.status_code == 200, response.text
        answer = response.json()
        assert answer["grounded"] is True
        assert any(citation in ref["citation"] for ref in answer["source_refs"])
        assert answer["speech_id"]
        answers[assistant_id] = answer

    project_path = "/api/pitch/sample-assistants/project-delivery/answer"
    assert guest.post(project_path, json={"question": "What is blocking the launch?"}).json()["grounded"] is True
    course = guest.post("/api/pitch/sample-assistants/course-companion/answer", json={
        "question": "What is blocking the launch?",
    }).json()
    assert course["grounded"] is False
    assert guest.post(project_path, json={"question": "What is blocking the launch?"}).json()["grounded"] is True

    spoken_text = []
    monkeypatch.setattr(pitch_routes, "_speech_audio", lambda text, voice=None: spoken_text.append(text) or (b"wav", "audio/wav"))
    speech = guest.post(
        f"/api/pitch/sample-assistants/project-delivery/answers/{answers['project-delivery']['speech_id']}/speech",
        json={"text": "untrusted caller text"},
    )
    assert speech.status_code == 200
    assert speech.content == b"wav"
    assert spoken_text == [answers["project-delivery"]["spoken_answer"]]
    wrong_assistant = guest.post(
        f"/api/pitch/sample-assistants/course-companion/answers/{answers['project-delivery']['speech_id']}/speech",
    )
    assert wrong_assistant.status_code == 404


def test_sample_assistant_templates_are_private_reviewable_and_atomic(clients, monkeypatch):
    first, second = clients
    templates = first.get("/api/pitch/assistant-templates").json()
    assert [template["id"] for template in templates] == [
        "team-onboarding", "project-delivery", "customer-kickoff", "course-companion", "consulting-services",
    ]
    created = first.post("/api/assistants/from-sample/team-onboarding")
    assert created.status_code == 200
    assistant = created.json()
    path = f"/api/assistants/{assistant['id']}"
    assert assistant["name"] == "Team & onboarding guide"
    assert {source["metadata"]["sample_id"] for source in assistant["sources"]} == {"team-handbook", "new-starter"}
    assert all(not source["approved"] for source in assistant["sources"])
    assert assistant["published"] is False
    assert first.post(f"{path}/answer", json={"question": "How do I request system access?"}).status_code == 409
    assert second.get(path).status_code == 404

    store_source = assistants._store_source
    stored = 0

    def fail_second_source(*args, **kwargs):
        nonlocal stored
        stored += 1
        if stored == 2:
            raise HTTPException(413, "source limit reached")
        return store_source(*args, **kwargs)

    monkeypatch.setattr(assistants, "_store_source", fail_second_source)
    assert first.post("/api/assistants/from-sample/team-onboarding").status_code == 413
    assert len(first.get("/api/assistants").json()) == 1


def test_sample_assistant_suggested_questions_have_named_support(clients):
    first, _ = clients
    expected = {
        "team-onboarding": [
            ("What should I do in my first week?", "new-starter-guide.pptx", "Slide 3", "review the team handbook"),
            ("How do I request system access?", "new-starter-guide.pptx", "Slide 4", "Morgan approves or adjusts the request"),
            ("How much notice should I give for planned leave?", "team-handbook.pptx", "Slide 4", "five working days ahead"),
        ],
        "project-delivery": [
            ("What is blocking the launch?", "weekly-project-update.pptx", "Slide 4", "CSV date bug is the main launch blocker"),
            ("Who owns the export retest, and when?", "weekly-project-update.pptx", "Slide 4", "Mei owns the fix; a retest is due 18 July"),
            ("What is the fallback if a check fails?", "weekly-project-update.pptx", "Slide 4", "onboard six teams first"),
        ],
        "customer-kickoff": [
            ("What outcome did the customer agree to by day 30?", "customer-success-plan.pptx", "Slide 2", "at least 14 of the 18 users"),
            ("Who sends the weekly recap?", "customer-success-plan.pptx", "Slide 5", "sends a written weekly recap"),
            ("When will finance approve the sales and returns definitions?", "customer-success-plan.pptx", "Slide 6", "Finance will approve them by day 10"),
        ],
        "course-companion": [
            ("What are the three steps in Lesson 3?", "course-lesson-guide.md", "Source section", "Use three steps"),
            ("How long does the practice activity last?", "course-lesson-guide.md", "Source section", "The practice takes 12 minutes"),
            ("What does a feature idea propose?", "course-lesson-guide.md", "Source section", "A feature idea proposes a solution"),
        ],
        "consulting-services": [
            ("How many interviews are included in the sprint?", "consulting-service-guide.md", "Source section", "six moderated 45-minute customer interviews"),
            ("What work is outside the fixed scope?", "consulting-service-guide.md", "Source section", "Participant recruiting, translation, prototype design"),
            ("What is the illustrative sample fee?", "consulting-service-guide.md", "Source section", "The fictional sample fee is $8,500"),
        ],
    }
    for template_id, questions in expected.items():
        created = first.post(f"/api/assistants/from-sample/{template_id}")
        assert created.status_code == 200, (template_id, created.text)
        assistant = created.json()
        path = f"/api/assistants/{assistant['id']}"
        for source in assistant["sources"]:
            assert first.patch(f"{path}/sources/{source['id']}", json={"approved": True}).status_code == 200
        for question, filename, citation, evidence in questions:
            answer = first.post(f"{path}/answer", json={"question": question}).json()
            assert answer["grounded"] is True, (template_id, question, answer)
            assert any(
                filename in ref["citation"] and citation in ref["citation"] and evidence in ref["text"]
                for ref in answer["source_refs"]
            ), (template_id, question, answer["source_refs"])
        if template_id == "team-onboarding":
            question = "How do I request system access?"
            initial = first.post(f"{path}/answer", json={"question": question}).json()
            follow_up = first.post(f"{path}/answer", json={
                "question": "And if the request is pending longer than two working days?",
                "history": [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": initial["spoken_answer"]},
                ],
            }).json()
            assert follow_up["grounded"] is True
            assert any("new-starter-guide.pptx" in ref["citation"] and "Slide 4" in ref["citation"]
                       for ref in follow_up["source_refs"])
            unsupported = first.post(f"{path}/answer", json={
                "question": "Does it guarantee account access tomorrow?",
                "history": [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": initial["spoken_answer"]},
                ],
            }).json()
            assert unsupported["grounded"] is False
            assert unsupported["source_refs"] == []
            assert unsupported["spoken_answer"] == unsupported["answer"]

    # The published snapshot uses the same source-qualified citations as private answers.
    assistant = first.post("/api/assistants/from-sample/team-onboarding").json()
    path = f"/api/assistants/{assistant['id']}"
    for source in assistant["sources"]:
        first.patch(f"{path}/sources/{source['id']}", json={"approved": True})
    token = first.post(f"{path}/publish").json()["url"].split("/")[-1]
    answer = first.post(f"/api/shared/{token}/answer", json={"question": "How much notice should I give for planned leave?"}).json()
    assert any("team-handbook.pptx" in ref["citation"] and "Slide 4" in ref["citation"] for ref in answer["source_refs"])


@pytest.mark.parametrize(("assistant_id", "question", "spoken_facts"), [
    ("project-delivery", "Who owns the export retest, and when?", ("Mei", "18 July")),
    ("project-delivery", "What is the fallback if a check fails?", ("six teams", "21 July")),
    ("customer-kickoff", "What outcome did the customer agree to by day 30?", ("14 of the 18 users", "day 30")),
    ("customer-kickoff", "Who sends the weekly recap?", ("Priya", "weekly recap")),
    ("course-companion", "What are the three steps in Lesson 3?", ("highlight the participant’s exact words", "supported by those observations")),
    ("consulting-services", "How long does the sprint take?", ("four-week",)),
])
def test_sample_voice_reply_speaks_the_requested_source_facts(clients, assistant_id, question, spoken_facts):
    guest = TestClient(app.app, base_url="http://localhost")

    response = guest.post(f"/api/pitch/sample-assistants/{assistant_id}/answer", json={"question": question})

    assert response.status_code == 200
    answer = response.json()
    assert answer["grounded"] is True
    spoken = answer["spoken_answer"].casefold()
    assert all(fact.casefold() in spoken for fact in spoken_facts), spoken
    assert not spoken.startswith("##")


def test_kokoro_speech_is_limited_to_grounded_owner_and_published_answers(clients, monkeypatch):
    first, second = clients
    assistant = first.post("/api/assistants", json={"name": "Customer guide"}).json()
    path = f"/api/assistants/{assistant['id']}"
    first.post(f"{path}/sources/files", files={
        "file": ("faq.txt", b"Customers can request a refund within 30 days.", "text/plain"),
    })
    source = first.get(path).json()["sources"][0]
    first.patch(f"{path}/sources/{source['id']}", json={"approved": True})
    warmed = []
    generated = []
    monkeypatch.setattr(assistants, "_speech_provider", lambda: "kokoro")
    monkeypatch.setattr(assistants, "_warm_kokoro_voice", lambda: warmed.append(True) or True)
    monkeypatch.setattr(assistants, "_speech_audio", lambda text: (generated.append(text) or b"kokoro-wav", "audio/wav"))

    monkeypatch.setenv("ASR_PROVIDER", "local")
    monkeypatch.setattr(pitch_routes, "find_spec", lambda name: object())
    monkeypatch.setattr(assistants, "_transcription_provider", lambda: "whisper-local")
    assert first.post(f"{path}/voice/warm").json() == {
        "provider": "kokoro", "warmed": True, "transcription_provider": "whisper-local",
        "transcription_ready": True, "transcription_error": None,
    }
    assert second.post(f"{path}/voice/warm").status_code == 404
    answer = first.post(f"{path}/answer", json={
        "question": "How long do customers have to request a refund?",
    }).json()
    speech_path = f"{path}/answers/{answer['answer_id']}/speech"
    spoofed_speech = first.post(speech_path, json={"text": "The product launches tomorrow."})
    assert spoofed_speech.status_code == 404
    assert generated == []
    speech = first.post(speech_path, json={"text": answer["spoken_answer"]})
    assert speech.status_code == 200
    assert speech.headers["content-type"] == "audio/wav"
    assert speech.content == b"kokoro-wav"
    assert generated == [answer["spoken_answer"]]
    assert second.post(speech_path, json={"text": answer["spoken_answer"]}).status_code == 404
    assert first.post(speech_path, json={"text": "x" * (assistants.MAX_SPOKEN_REPLY_CHARS + 1)}).status_code == 422
    monkeypatch.setattr(assistants, "_speech_provider", lambda: "browser")
    assert first.post(speech_path, json={"text": answer["spoken_answer"]}).status_code == 409
    monkeypatch.setattr(assistants, "_speech_provider", lambda: "kokoro")

    unsupported = first.post(f"{path}/answer", json={"question": "What is the product's launch date?"}).json()
    blocked = first.post(f"{path}/answers/{unsupported['answer_id']}/speech", json={"text": "The launch is tomorrow."})
    assert blocked.status_code == 404
    assert len(generated) == 1

    token = first.post(f"{path}/publish").json()["url"].split("/")[-1]
    assert first.post(f"/api/shared/{token}/voice/warm").json() == {
        "provider": "kokoro", "warmed": True, "transcription_provider": "whisper-local",
        "transcription_ready": True, "transcription_error": None,
    }
    shared_answer = first.post(f"/api/shared/{token}/answer", json={
        "question": "How long do customers have to request a refund?",
    }).json()
    shared_path = f"/api/shared/{token}/answers/{shared_answer['answer_id']}/speech"
    assert first.post(shared_path, json={"text": "The product launches tomorrow."}).status_code == 404
    shared_speech = first.post(shared_path, json={"text": shared_answer["spoken_answer"]})
    assert shared_speech.status_code == 200
    assert generated[-1] == shared_answer["spoken_answer"]
    first.delete(f"{path}/publish")
    assert first.post(shared_path, json={"text": shared_answer["spoken_answer"]}).status_code == 404


def test_voice_warm_reports_missing_hosted_transcription_setup(clients, monkeypatch):
    first, _ = clients
    assistant = first.post("/api/assistants", json={"name": "Team handbook"}).json()
    monkeypatch.setenv("TTS_PROVIDER", "kokoro")
    monkeypatch.setenv("ASR_PROVIDER", "huggingface")
    monkeypatch.setenv("HUGGINGFACE_API_TOKEN", "")
    monkeypatch.setattr(assistants, "_speech_provider", lambda: "kokoro")
    monkeypatch.setattr(assistants, "_warm_kokoro_voice", lambda: True)

    result = first.post(f"/api/assistants/{assistant['id']}/voice/warm").json()

    assert result["provider"] == "kokoro"
    assert result["transcription_provider"] == "huggingface"
    assert result["transcription_ready"] is False
    assert result["transcription_error"] == "Set HUGGINGFACE_API_TOKEN in .env to transcribe audio."


def test_homepage_and_studio_use_the_same_kokoro_synthesizer(clients, monkeypatch):
    first, _ = clients
    assistant = first.post("/api/assistants", json={"name": "Team handbook"}).json()
    path = f"/api/assistants/{assistant['id']}"
    first.post(f"{path}/sources/files", files={
        "file": ("guide.txt", b"Employees receive 20 days of annual leave.", "text/plain"),
    })
    source = first.get(path).json()["sources"][0]
    first.patch(f"{path}/sources/{source['id']}", json={"approved": True})
    monkeypatch.setenv("TTS_PROVIDER", "kokoro")
    calls = []
    monkeypatch.setattr(pitch_routes, "_kokoro_audio", lambda text: calls.append(text) or b"same-kokoro-wav")
    answer = first.post(f"{path}/answer", json={"question": "How much annual leave do employees receive?"}).json()

    homepage_speech = first.post(
        "/api/voice/speak", json={"text": answer["spoken_answer"]},
        headers={"Authorization": "Bearer pilot-invite"},
    )
    studio_speech = first.post(
        f"{path}/answers/{answer['answer_id']}/speech", json={"text": answer["spoken_answer"]},
    )

    assert homepage_speech.status_code == studio_speech.status_code == 200
    assert homepage_speech.content == studio_speech.content == b"same-kokoro-wav"
    assert calls == [answer["spoken_answer"], answer["spoken_answer"]]


def test_voice_transcription_is_scoped_to_owner_or_published_link(clients, monkeypatch):
    first, second = clients
    assistant = first.post("/api/assistants", json={"name": "Customer guide"}).json()
    path = f"/api/assistants/{assistant['id']}"
    first.post(f"{path}/sources/files", files={
        "file": ("faq.txt", b"Customers can request a refund within 30 days.", "text/plain"),
    })
    source = first.get(path).json()["sources"][0]
    first.patch(f"{path}/sources/{source['id']}", json={"approved": True})
    token = first.post(f"{path}/publish").json()["url"].split("/")[-1]
    calls = []

    async def transcribe(file):
        calls.append(file.filename)
        return {"text": "How long is the refund window?", "provider": "whisper-local"}

    monkeypatch.setattr(assistants, "_transcribe_audio_file", transcribe)
    audio = {"file": ("question.webm", b"recording", "audio/webm")}
    owner_result = first.post(f"{path}/voice/transcribe", files=audio)
    assert owner_result.status_code == 200
    assert owner_result.json() == {"text": "How long is the refund window?", "provider": "whisper-local"}
    assert second.post(f"{path}/voice/transcribe", files=audio).status_code == 404

    guest = TestClient(app.app, base_url="http://localhost")
    shared_result = guest.post(f"/api/shared/{token}/voice/transcribe", files=audio)
    assert shared_result.status_code == 200
    assert shared_result.json()["text"] == "How long is the refund window?"
    first.delete(f"{path}/publish")
    assert guest.post(f"/api/shared/{token}/voice/transcribe", files=audio).status_code == 404
    assert calls == ["question.webm", "question.webm"]


def test_speech_budget_is_per_assistant_and_expires(monkeypatch):
    assistant_id = "speech-budget-test"
    now = [1000.0]
    assistants._speech_starts.pop(assistant_id, None)
    monkeypatch.setattr(assistants.time, "monotonic", lambda: now[0])
    for _ in range(assistants.MAX_ASSISTANT_SPEECH_PER_MINUTE):
        assert assistants._take_speech_budget(assistant_id)
    assert not assistants._take_speech_budget(assistant_id)
    assert assistants._take_speech_budget("another-assistant")
    now[0] += 60
    assert assistants._take_speech_budget(assistant_id)
    assistants._speech_starts.pop(assistant_id, None)
    assistants._speech_starts.pop("another-assistant", None)


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


def _book_pdf_with_scanned_flowchart() -> bytes:
    document = pymupdf.open()
    first = document.new_page()
    first.insert_textbox(
        pymupdf.Rect(72, 50, 525, 400),
        "Chapter 1: Refunds. Customers may request a refund within 30 days of delivery. "
        "Items must be unused and proof of purchase must be provided. "
        "Support reviews the request within 2 business days.",
        fontsize=12,
    )
    second = document.new_page()
    second.insert_textbox(
        pymupdf.Rect(72, 50, 525, 400),
        "Chapter 2: Review process. First verify the customer identity. "
        "Then check the order date and item condition. If approved, issue the refund "
        "to the original payment method. Notify the customer by email.",
        fontsize=12,
    )

    diagram = pymupdf.open()
    page = diagram.new_page(width=595, height=842)
    labels = [
        "START: Request received",
        "STEP 1: Verify customer identity",
        "STEP 2: Check order date and item condition",
        "DECISION: Within 30 days and unused?",
        "YES: Approve and issue refund",
        "END: Email customer",
    ]
    top = 35
    for index, label in enumerate(labels):
        rect = pymupdf.Rect(65, top, 530, top + 92)
        page.draw_rect(rect, color=(0, 0, 0), width=2)
        label_rect = pymupdf.Rect(rect.x0 + 12, rect.y0 + 20, rect.x1 - 12, rect.y1 - 20)
        page.insert_textbox(label_rect, label, fontsize=16, align=1)
        top += 132
        if index < len(labels) - 1:
            page.draw_line((297, top - 40), (297, top - 5), color=(0, 0, 0), width=3)
    image = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False).tobytes("png")
    scanned_page = document.new_page(width=595, height=842)
    scanned_page.insert_image(scanned_page.rect, stream=image)
    mixed_page = document.new_page(width=595, height=842)
    mixed_page.insert_textbox(
        pymupdf.Rect(55, 30, 540, 100),
        "Figure 1. The flow diagram shows the refund review process.",
        fontsize=12,
    )
    mixed_page.insert_image(pymupdf.Rect(55, 120, 540, 810), stream=image)
    document_bytes = document.tobytes()
    document.close()
    diagram.close()
    return document_bytes


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract OCR is not installed")
def test_uploaded_book_pdf_indexes_scanned_flowchart_and_explains_chapter(clients):
    first, _ = clients
    assistant = first.post("/api/assistants", json={"name": "Refund handbook"}).json()
    upload = first.post(
        f"/api/assistants/{assistant['id']}/sources/files",
        files={"file": ("refund-handbook.pdf", _book_pdf_with_scanned_flowchart(), "application/pdf")},
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["metadata"]["ocr_pages"] == [3, 4]

    source = first.get(f"/api/assistants/{assistant['id']}").json()["sources"][0]
    assert "Verify customer identity" in source["sections"][-1]["text"]
    assert "Image text:" in source["sections"][-1]["text"]
    assert first.patch(
        f"/api/assistants/{assistant['id']}/sources/{source['id']}", json={"approved": True}
    ).status_code == 200

    chapter = first.post(f"/api/assistants/{assistant['id']}/answer", json={
        "question": "Explain Chapter 1 in simple terms.",
    }).json()
    assert chapter["grounded"] is True
    assert "Page 1" in chapter["source_refs"][0]["citation"]
    assert "30 days" in chapter["answer"]
    assert "30 days" in chapter["spoken_answer"]

    paraphrased = first.post(f"/api/assistants/{assistant['id']}/answer", json={
        "question": "How long does a customer have to request a refund?",
    }).json()
    assert paraphrased["grounded"] is True
    assert "30 days" in paraphrased["answer"]
    assert "Customers may request" in paraphrased["spoken_answer"]
    assert "Approve and issue refund" not in paraphrased["spoken_answer"]

    diagram_answer = first.post(f"/api/assistants/{assistant['id']}/answer", json={
        "question": "What steps are shown in the flow diagram?",
    }).json()
    assert diagram_answer["grounded"] is True
    assert "Page 3" in diagram_answer["source_refs"][0]["citation"]
    assert "Verify customer identity" in diagram_answer["answer"]


def test_scanned_pdf_without_tesseract_reports_that_image_text_is_missing(monkeypatch):
    monkeypatch.setattr(pitch_routes.shutil, "which", lambda _: None)
    sections, metadata = pitch_routes._extract_pdf(_book_pdf_with_scanned_flowchart())

    assert [section.citation for section in sections] == ["Page 1", "Page 2", "Page 4"]
    assert not any("Verify customer identity" in section.text for section in sections)
    assert metadata["image_only_pages"] == [3]
    assert any("Tesseract is not installed" in warning for warning in metadata["warnings"])


def test_private_assistant_uses_opted_in_generation_to_explain_relevant_source(clients, monkeypatch):
    first, _ = clients
    monkeypatch.setenv("ANSWER_GENERATION_PROVIDER", "huggingface")
    monkeypatch.setenv("HUGGINGFACE_API_TOKEN", "test-token")
    contexts = []

    def explain(question, context):
        contexts.append((question, context))
        return "In simple terms, Chapter 1 says refunds are allowed for qualifying purchases within 30 days.", "huggingface"

    monkeypatch.setattr(pitch_routes, "_answer_with_provider", explain)
    assistant = first.post("/api/assistants", json={"name": "Handbook"}).json()
    first.post(f"/api/assistants/{assistant['id']}/sources/files", files={
        "file": (
            "book.txt",
            b"Chapter 1: Refunds are available within 30 days.\n\nChapter 2: Requests are reviewed within two business days.",
            "text/plain",
        ),
    })
    source = first.get(f"/api/assistants/{assistant['id']}").json()["sources"][0]
    first.patch(f"/api/assistants/{assistant['id']}/sources/{source['id']}", json={"approved": True})

    answer = first.post(f"/api/assistants/{assistant['id']}/answer", json={
        "question": "Explain Chapter 1 in simple terms.",
    }).json()

    assert answer["provider"] == "huggingface"
    assert answer["answer"].startswith("In simple terms")
    assert contexts and all("Chapter 2" not in excerpt for excerpt in contexts[0][1])
    assert "Chapter 1" in answer["source_refs"][0]["text"]
