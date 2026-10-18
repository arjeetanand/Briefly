import base64
import io
import json
import wave
import zipfile

from pathlib import Path

import numpy as np
import pymupdf
from fastapi.testclient import TestClient

import app
from routes import pitch as pitch_routes


client = TestClient(app.app)


def setup_function() -> None:
    app.store.path = Path("missing-pitch.txt")
    app.store.text = ""
    app.store.sections = []
    app.store.metadata = {"format": "text", "sections": 0, "warnings": []}
    app.store.source = "test"


def test_root_serves_the_live_pitchroom_interface() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Pitchroom AI" in response.text
    assert "/static/app.js" in response.text


def test_document_upload_and_grounded_answer() -> None:
    upload = client.post(
        "/api/pitch/document",
        json={"document": "The product helps founders prepare for investor meetings."},
    )
    assert upload.status_code == 200

    response = client.post("/api/voice/answer", json={"question": "Who does the product help?"})

    assert response.status_code == 200
    assert response.json()["grounded"] is True
    assert "founders" in response.json()["answer"]


def test_answer_declines_unknown_question() -> None:
    client.post("/api/pitch/document", json={"document": "The product helps founders prepare for investor meetings."})

    response = client.post("/api/voice/answer", json={"question": "What is the launch date?"})

    assert response.status_code == 200
    assert response.json()["grounded"] is False
    assert "could not find" in response.json()["answer"]


def test_answer_stays_within_the_live_studio_voice_budget(monkeypatch) -> None:
    monkeypatch.setenv("ANSWER_GENERATION_PROVIDER", "extractive")
    long_source_sentence = "Pitchroom evidence supports founders " + ("with documented details " * 30) + "."
    client.post("/api/pitch/document", json={"document": " ".join([long_source_sentence] * 4)})

    response = client.post("/api/voice/answer", json={"question": "What Pitchroom evidence supports founders?"})

    assert response.status_code == 200
    answer = response.json()["answer"]
    assert len(answer) <= pitch_routes.MAX_SPOKEN_ANSWER_CHARS
    assert answer.endswith(".")
    assert "Pitchroom evidence supports founders" in answer
    assert "ask a more specific question" in response.json()["spoken_answer"]


def test_live_voice_reads_a_concise_complete_answer_and_keeps_full_evidence_visible(monkeypatch) -> None:
    monkeypatch.setenv("ANSWER_GENERATION_PROVIDER", "extractive")
    client.post(
        "/api/pitch/document",
        json={
            "document": (
                "The website review is due Friday. The design review is due Monday. "
                "The launch review is due Tuesday. The security review is due Thursday."
            )
        },
    )

    response = client.post(
        "/api/voice/answer",
        json={"question": "When is the review due?"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "The launch review is due Tuesday" in data["answer"]
    assert any("The launch review is due Tuesday" in source for source in data["sources"])
    assert "The launch review is due Tuesday" not in data["spoken_answer"]
    assert not data["spoken_answer"].startswith("According to the approved source")
    assert data["spoken_answer"].endswith(".")
    assert len(data["spoken_answer"]) <= pitch_routes.MAX_SPOKEN_REPLY_CHARS
    assert len(pitch_routes._sentence_parts(data["spoken_answer"])) <= pitch_routes.MAX_SPOKEN_REPLY_SENTENCES


def test_answer_declines_unknown_fact_when_the_subject_name_repeats() -> None:
    client.post(
        "/api/pitch/document",
        json={
            "document": (
                "Pitchroom AI helps founders prepare for investor meetings. "
                "Pitchroom AI answers questions from an approved source. "
                "Pitchroom AI speaks grounded answers aloud. "
                "Pitchroom AI stores the active demo source in memory."
            )
        },
    )

    response = client.post(
        "/api/voice/answer",
        json={"question": "What is Pitchroom AI's Series B valuation?"},
    )

    assert response.status_code == 200
    assert response.json()["grounded"] is False
    assert "could not find" in response.json()["answer"]


def test_answer_declines_unknown_fact_with_a_possessive_product_name() -> None:
    client.post(
        "/api/pitch/document",
        json={
            "document": (
                "Pitchroom AI helps founders prepare for investor meetings. "
                "Pitchroom AI's promise is to answer only from the approved source."
            )
        },
    )

    response = client.post(
        "/api/voice/answer",
        json={"question": "What is Pitchroom AI's Series B valuation?"},
    )

    assert response.status_code == 200
    assert response.json()["grounded"] is False
    assert "could not find" in response.json()["answer"]


def test_answer_keeps_the_best_source_section_for_a_scripted_demo_question() -> None:
    client.post(
        "/api/pitch/document",
        json={
            "document": (
                "Pitchroom AI solves the problem that static pitch decks can leave founders unable to answer unexpected questions. "
                "Pitchroom AI helps founder-led startup teams prepare for investor meetings, customer conversations, and internal demos. "
                "Pitchroom AI's promise is to answer only from the approved source."
            )
        },
    )

    response = client.post(
        "/api/voice/answer",
        json={"question": "What kind of teams does Pitchroom AI help?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is True
    assert body["sources"] == [
        "Pitchroom AI helps founder-led startup teams prepare for investor meetings, customer conversations, and internal demos."
    ]
    assert "static pitch decks" not in body["answer"]


def test_retrieval_ignores_question_fillers_when_finding_file_support() -> None:
    client.post(
        "/api/pitch/document",
        json={
            "document": (
                "Pitchroom AI turns an approved pitch deck or document into a voice conversation by accepting PPTX, PDF, DOCX, Markdown, or plain-text sources. "
                "Pitchroom AI keeps the supporting source visible during every answer."
            )
        },
    )

    response = client.post("/api/voice/answer", json={"question": "What file types can Pitchroom accept?"})

    assert response.status_code == 200
    assert response.json()["grounded"] is True
    assert "PPTX" in response.json()["answer"]


def test_pdf_upload_extracts_text() -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "The pitch supports customer demos.")
    pdf_bytes = document.tobytes()
    document.close()

    response = client.post(
        "/api/pitch/file",
        files={"file": ("pitch.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 200
    pitch = client.get("/api/pitch").json()
    assert "customer demos" in pitch["text"]
    assert pitch["metadata"]["format"] == "pdf"
    assert pitch["sections"][0]["citation"] == "Page 1"


def test_pptx_upload_preserves_slide_sections_and_citations() -> None:
    response = client.post(
        "/api/pitch/file",
        files={
            "file": (
                "investor-deck.pptx",
                _pptx_bytes(
                    "The problem is slow investor preparation.",
                    "Pitchroom answers founder questions from the approved deck.",
                ),
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "investor-deck.pptx"
    assert body["metadata"]["format"] == "pptx"
    assert body["metadata"]["slides"] == 2
    assert body["metadata"]["warnings"] == []

    answer = client.post("/api/voice/answer", json={"question": "What does Pitchroom answer?"})
    assert answer.status_code == 200
    assert answer.json()["source_refs"][0]["citation"] == "Slide 2"


def test_docx_upload_extracts_paragraphs() -> None:
    response = client.post(
        "/api/pitch/file",
        files={
            "file": (
                "brief.docx",
                _docx_bytes("Customer interviews reveal a trust gap.", "The rehearsal keeps evidence visible."),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["format"] == "docx"
    assert body["chunks"] == 2
    assert client.get("/api/pitch").json()["sections"][1]["citation"] == "Document section 2"


def test_document_upload_enforces_the_configured_size_limit(monkeypatch) -> None:
    monkeypatch.setenv("MAX_DOCUMENT_BYTES", "4")

    response = client.post(
        "/api/pitch/file",
        files={"file": ("pitch.txt", b"12345", "text/plain")},
    )

    assert response.status_code == 413
    assert "at most 4 bytes" in response.json()["detail"]


def test_markdown_upload_accepts_generic_content_type() -> None:
    response = client.post(
        "/api/pitch/file",
        files={"file": ("pitch.md", b"# The pitch\nIt helps teams rehearse demos.", "application/octet-stream")},
    )

    assert response.status_code == 200
    assert "rehearse demos" in client.get("/api/pitch").json()["text"]


def test_unsupported_file_type_is_rejected() -> None:
    response = client.post(
        "/api/pitch/file",
        files={"file": ("pitch.zip", b"not a pitch", "application/zip")},
    )

    assert response.status_code == 415


def test_speak_requires_provider_configuration(monkeypatch) -> None:
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    monkeypatch.delenv("HUGGINGFACE_API_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("TTS_PROVIDER", "auto")
    monkeypatch.setenv("HUGGINGFACE_TTS_MODE", "api")

    response = client.post("/api/voice/speak", json={"text": "Read this pitch."})

    assert response.status_code == 503


def _wav_bytes() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\x00\x00" * 16)
    return buffer.getvalue()


def _pptx_bytes(*slides: str) -> bytes:
    """Small OOXML fixture that exercises the same parser as real PPTX files."""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for index, text in enumerate(slides, start=1):
            escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            archive.writestr(
                f"ppt/slides/slide{index}.xml",
                (
                    '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                    f"<p:cSld><a:p><a:r><a:t>{escaped}</a:t></a:r></a:p></p:cSld></p:sld>"
                ),
            )
    return buffer.getvalue()


def _docx_bytes(*paragraphs: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        body = "".join(
            f'<w:p><w:r><w:t>{text}</w:t></w:r></w:p>'
            for text in paragraphs
        )
        archive.writestr(
            "word/document.xml",
            (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f"<w:body>{body}</w:body></w:document>"
            ),
        )
    return buffer.getvalue()


def test_sarvam_speech_response_advertises_wav(monkeypatch) -> None:
    monkeypatch.setenv("SARVAM_API_KEY", "test-key")
    monkeypatch.setenv("TTS_PROVIDER", "auto")
    monkeypatch.setattr(pitch_routes, "_sarvam_audio", lambda text: _wav_bytes())

    response = client.post("/api/voice/speak", json={"text": "Read this pitch."})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content.startswith(b"RIFF")


def test_sarvam_payload_uses_current_language_code_field(monkeypatch) -> None:
    monkeypatch.setenv("SARVAM_API_KEY", "test-key")
    monkeypatch.setenv("TTS_PROVIDER", "auto")
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self) -> bytes:
            return json.dumps({"audios": [base64.b64encode(_wav_bytes()).decode()]}).encode()

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode())
        return FakeResponse()

    monkeypatch.setattr(pitch_routes.urllib.request, "urlopen", fake_urlopen)

    assert pitch_routes._sarvam_audio("Read this pitch.") == _wav_bytes()
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["language_code"] == "en-IN"
    assert "target_language_code" not in payload


def test_piper_speech_response_uses_local_http_service(monkeypatch) -> None:
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    monkeypatch.delenv("HUGGINGFACE_API_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("TTS_PROVIDER", "piper")
    monkeypatch.setenv("PIPER_TTS_URL", "http://127.0.0.1:5000/synthesize")
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self) -> bytes:
            return _wav_bytes()

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode())
        return FakeResponse()

    monkeypatch.setattr(pitch_routes.urllib.request, "urlopen", fake_urlopen)

    response = client.post("/api/voice/speak", json={"text": "Read this pitch."})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content.startswith(b"RIFF")
    assert captured["url"] == "http://127.0.0.1:5000/synthesize"
    assert captured["payload"] == {"text": "Read this pitch."}


def test_kokoro_speech_response_uses_the_local_studio_voice(monkeypatch) -> None:
    monkeypatch.setenv("TTS_PROVIDER", "kokoro")
    monkeypatch.setattr(pitch_routes, "_kokoro_audio", lambda text: _wav_bytes())

    response = client.post("/api/voice/speak", json={"text": "Read this pitch."})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content.startswith(b"RIFF")


def test_kokoro_converts_configured_pipeline_output_to_24khz_wav(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakePipeline:
        def __call__(self, text, voice, speed, split_pattern):
            captured.update({"text": text, "voice": voice, "speed": speed, "split_pattern": split_pattern})
            yield "Pitchroom is ready.", "phonemes", np.array([-1.0, 0.0, 1.0], dtype=np.float32)

    monkeypatch.setattr(pitch_routes, "_kokoro_pipeline", lambda *args: FakePipeline())
    audio = pitch_routes._kokoro_audio_with_options(
        "Pitchroom is ready.",
        ("a", "af_heart", pitch_routes.KOKORO_MODEL_REPO, 0.98, "cpu"),
    )

    with wave.open(io.BytesIO(audio), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 24_000
        assert wav_file.getnframes() == 3
    assert captured == {
        "text": "Pitchroom is ready.",
        "voice": "af_heart",
        "speed": 0.98,
        "split_pattern": None,
    }


def test_kokoro_refuses_oversized_live_speech_before_loading_a_model(monkeypatch) -> None:
    monkeypatch.setenv("TTS_PROVIDER", "kokoro")
    loader_calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(pitch_routes, "_kokoro_pipeline", lambda *args: loader_calls.append(args))

    response = client.post("/api/voice/speak", json={"text": "x" * (pitch_routes.MAX_KOKORO_TEXT_CHARS + 1)})

    assert response.status_code == 503
    assert "optimized for live replies" in response.json()["detail"]
    assert loader_calls == []


def test_kokoro_limits_a_long_pitch_read_before_it_can_block_live_answers(monkeypatch) -> None:
    monkeypatch.setenv("TTS_PROVIDER", "kokoro")
    client.post("/api/pitch/document", json={"document": "x" * (pitch_routes.MAX_KOKORO_TEXT_CHARS + 1)})

    response = client.post("/api/pitch/read")

    assert response.status_code == 503
    assert "optimized for live replies" in response.json()["detail"]


def test_kokoro_failure_does_not_fall_through_to_hosted_tts(monkeypatch) -> None:
    monkeypatch.setenv("TTS_PROVIDER", "kokoro")
    monkeypatch.setenv("SARVAM_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        pitch_routes,
        "_kokoro_audio",
        lambda text: (_ for _ in ()).throw(RuntimeError("Kokoro model is warming")),
    )
    monkeypatch.setattr(
        pitch_routes,
        "_sarvam_audio",
        lambda text: (_ for _ in ()).throw(AssertionError("Sarvam must not be called")),
    )
    monkeypatch.setattr(
        pitch_routes,
        "_openai_audio",
        lambda text, voice: (_ for _ in ()).throw(AssertionError("OpenAI must not be called")),
    )

    response = client.post("/api/voice/speak", json={"text": "Read this pitch."})

    assert response.status_code == 503
    assert "Kokoro model is warming" in response.json()["detail"]


def test_kokoro_warm_route_preloads_only_the_selected_local_voice(monkeypatch) -> None:
    monkeypatch.setenv("TTS_PROVIDER", "kokoro")
    monkeypatch.setenv("ASR_PROVIDER", "local")
    monkeypatch.setattr(pitch_routes, "find_spec", lambda name: object())
    warmed: list[bool] = []
    monkeypatch.setattr(pitch_routes, "_warm_kokoro_voice", lambda: warmed.append(True) or True)

    response = client.post("/api/voice/warm")

    assert response.status_code == 200
    assert response.json() == {
        "provider": "kokoro", "warmed": True, "ready": True,
        "transcription_provider": "whisper-local", "transcription_ready": True, "transcription_error": None,
    }
    assert warmed == [True]


def test_voice_warm_disables_local_transcription_without_optional_dependency(monkeypatch) -> None:
    monkeypatch.setenv("TTS_PROVIDER", "browser")
    monkeypatch.setenv("ASR_PROVIDER", "local")
    monkeypatch.setattr(pitch_routes, "find_spec", lambda name: None)

    response = client.post("/api/voice/warm")

    assert response.status_code == 200
    assert response.json()["transcription_ready"] is False
    assert response.json()["transcription_error"] == (
        "Local transcription needs backend/requirements-whisper.txt. Install it and restart the app."
    )


def test_kokoro_warm_failure_keeps_the_selected_provider_visible(monkeypatch) -> None:
    monkeypatch.setenv("TTS_PROVIDER", "kokoro")
    monkeypatch.setattr(
        pitch_routes,
        "_warm_kokoro_voice",
        lambda: (_ for _ in ()).throw(RuntimeError("Kokoro model is unavailable.")),
    )

    response = client.post("/api/voice/warm")

    assert response.status_code == 503
    assert response.headers["x-speech-provider"] == "kokoro"
    assert response.json()["detail"] == "Kokoro model is unavailable."


def test_kokoro_warmup_synthesizes_once_per_resolved_configuration(monkeypatch) -> None:
    options = ("a", "af_heart", pitch_routes.KOKORO_MODEL_REPO, 0.98, "cpu")
    calls: list[tuple[str, tuple[str, str, str, float, str]]] = []
    pitch_routes._kokoro_warmed.clear()
    monkeypatch.setattr(pitch_routes, "_kokoro_options", lambda: options)
    monkeypatch.setattr(
        pitch_routes,
        "_kokoro_audio_with_options",
        lambda text, configured_options: calls.append((text, configured_options)) or _wav_bytes(),
    )

    assert pitch_routes._warm_kokoro_voice() is True
    assert pitch_routes._warm_kokoro_voice() is False

    assert calls == [(pitch_routes.KOKORO_WARMUP_TEXT, options)]
    pitch_routes._kokoro_warmed.clear()


def test_health_returns_only_service_status() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_sarvam_failure_falls_back_to_openai(monkeypatch) -> None:
    monkeypatch.setenv("SARVAM_API_KEY", "test-key")
    monkeypatch.setenv("TTS_PROVIDER", "auto")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("HUGGINGFACE_API_TOKEN", raising=False)
    monkeypatch.setenv("HUGGINGFACE_TTS_MODE", "api")
    monkeypatch.setattr(
        pitch_routes,
        "_sarvam_audio",
        lambda text: (_ for _ in ()).throw(RuntimeError("Sarvam rejected the voice")),
    )
    monkeypatch.setattr(pitch_routes, "_openai_audio", lambda text, voice: b"ID3-fallback-audio")

    response = client.post("/api/voice/speak", json={"text": "Read this pitch."})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert response.content == b"ID3-fallback-audio"


def test_speak_aggregates_errors_only_after_all_configured_providers_fail(monkeypatch) -> None:
    monkeypatch.setenv("SARVAM_API_KEY", "test-key")
    monkeypatch.setenv("TTS_PROVIDER", "auto")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("HUGGINGFACE_API_TOKEN", raising=False)
    monkeypatch.setenv("HUGGINGFACE_TTS_MODE", "api")
    monkeypatch.setattr(
        pitch_routes,
        "_sarvam_audio",
        lambda text: (_ for _ in ()).throw(RuntimeError("Sarvam rejected the voice")),
    )
    monkeypatch.setattr(
        pitch_routes,
        "_openai_audio",
        lambda text, voice: (_ for _ in ()).throw(RuntimeError("OpenAI is unavailable")),
    )

    response = client.post("/api/voice/speak", json={"text": "Read this pitch."})

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "All configured text-to-speech providers failed" in detail
    assert "Sarvam rejected the voice" in detail
    assert "OpenAI is unavailable" in detail


def test_openai_is_used_when_local_huggingface_tts_is_unavailable(monkeypatch) -> None:
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    monkeypatch.delenv("HUGGINGFACE_API_TOKEN", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("TTS_PROVIDER", "auto")
    monkeypatch.setenv("HUGGINGFACE_TTS_MODE", "local")
    monkeypatch.setattr(
        pitch_routes,
        "_local_huggingface_audio",
        lambda text: (_ for _ in ()).throw(RuntimeError("local provider unavailable")),
    )
    monkeypatch.setattr(pitch_routes, "_openai_audio", lambda text, voice: b"ID3-test-audio")

    response = client.post("/api/voice/speak", json={"text": "Read this pitch."})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert response.content == b"ID3-test-audio"


def test_answer_is_extractive_by_default_even_when_huggingface_is_configured(monkeypatch) -> None:
    monkeypatch.setenv("HUGGINGFACE_API_TOKEN", "test-token")
    monkeypatch.delenv("ANSWER_GENERATION_PROVIDER", raising=False)
    monkeypatch.setattr(
        pitch_routes,
        "_answer_with_provider",
        lambda question, context: (_ for _ in ()).throw(AssertionError("provider should be opt-in")),
    )
    client.post(
        "/api/pitch/document",
        json={"document": "The product helps founders prepare for investor meetings."},
    )

    response = client.post("/api/voice/answer", json={"question": "Who does the product help?"})

    assert response.status_code == 200
    assert response.json()["provider"] == "extractive"
    assert "founders" in response.json()["answer"]


def test_demo_route_restores_the_included_brief_after_an_upload() -> None:
    client.post("/api/pitch/document", json={"document": "An unrelated rehearsal source."})

    response = client.post("/api/pitch/demo")

    assert response.status_code == 200
    assert response.json()["source"] == "pitch.txt"
    pitch = client.get("/api/pitch").json()
    assert "Pitchroom AI solves the problem" in pitch["text"]


def test_huggingface_answer_generation_requires_explicit_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("HUGGINGFACE_API_TOKEN", "test-token")
    monkeypatch.setenv("ANSWER_GENERATION_PROVIDER", "huggingface")
    monkeypatch.setattr(
        pitch_routes,
        "_answer_with_provider",
        lambda question, context: ("A generated, grounded answer.", "huggingface"),
    )
    client.post(
        "/api/pitch/document",
        json={"document": "The product helps founders prepare for investor meetings."},
    )

    response = client.post("/api/voice/answer", json={"question": "Who does the product help?"})

    assert response.status_code == 200
    assert response.json()["provider"] == "huggingface"
    assert response.json()["answer"] == "A generated, grounded answer."


def test_invalid_huggingface_transcription_response_is_a_service_error(monkeypatch) -> None:
    monkeypatch.setenv("ASR_PROVIDER", "huggingface")
    monkeypatch.setenv("HUGGINGFACE_API_TOKEN", "test-token")
    monkeypatch.setattr(pitch_routes, "_huggingface_request", lambda model, payload, content_type: b"not-json")

    response = client.post(
        "/api/voice/transcribe",
        files={"file": ("question.wav", b"RIFF", "audio/wav")},
    )

    assert response.status_code == 503
    assert "invalid transcription" in response.json()["detail"]


def test_transcribe_rejects_non_audio_upload_before_provider_call() -> None:
    response = client.post(
        "/api/voice/transcribe",
        files={"file": ("question.txt", b"not an audio recording", "text/plain")},
    )

    assert response.status_code == 415
    assert "audio recording" in response.json()["detail"]


def test_transcribe_rejects_oversized_audio_upload(monkeypatch) -> None:
    monkeypatch.setenv("HUGGINGFACE_API_TOKEN", "test-token")
    monkeypatch.setenv("MAX_AUDIO_BYTES", "4")
    monkeypatch.setattr(
        pitch_routes,
        "_huggingface_transcription",
        lambda audio, content_type: (_ for _ in ()).throw(AssertionError("oversized audio was sent upstream")),
    )

    response = client.post(
        "/api/voice/transcribe",
        files={"file": ("question.wav", b"RIFF!", "audio/wav")},
    )

    assert response.status_code == 413
    assert "at most 4 bytes" in response.json()["detail"]


def test_huggingface_text_accepts_object_response(monkeypatch) -> None:
    monkeypatch.setenv("HUGGINGFACE_API_TOKEN", "test-token")
    monkeypatch.setattr(
        pitch_routes,
        "_huggingface_request",
        lambda model, payload, content_type: b'{"generated_text":"A concise answer."}',
    )

    assert pitch_routes._huggingface_text("What is it?", ["It is a pitch assistant."]) == "A concise answer."


def test_huggingface_timeout_is_a_service_error(monkeypatch) -> None:
    monkeypatch.setenv("ASR_PROVIDER", "huggingface")
    monkeypatch.setenv("HUGGINGFACE_API_TOKEN", "test-token")
    monkeypatch.setattr(
        pitch_routes.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError()),
    )

    response = client.post(
        "/api/voice/transcribe",
        files={"file": ("question.wav", b"RIFF", "audio/wav")},
    )

    assert response.status_code == 503
    assert "could not be reached" in response.json()["detail"]


def test_local_transcription_needs_no_token_and_releases_slot(monkeypatch) -> None:
    monkeypatch.setenv("ASR_PROVIDER", "local")
    monkeypatch.setattr(pitch_routes, "find_spec", lambda name: object())
    monkeypatch.delenv("HUGGINGFACE_API_TOKEN", raising=False)
    pitch_routes._transcription_starts.clear()
    monkeypatch.setattr(
        pitch_routes, "_huggingface_transcription",
        lambda *args: (_ for _ in ()).throw(AssertionError("hosted transcription called")),
    )
    monkeypatch.setattr(pitch_routes, "_local_transcription", lambda *args: "Who does it help?")
    response = client.post(
        "/api/voice/transcribe", files={"file": ("question.wav", _wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 200
    assert response.json() == {"text": "Who does it help?", "provider": "whisper-local"}
    monkeypatch.setattr(
        pitch_routes, "_local_transcription",
        lambda *args: (_ for _ in ()).throw(RuntimeError("Local Whisper did not detect speech.")),
    )
    response = client.post(
        "/api/voice/transcribe", files={"file": ("question.wav", _wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 503
    assert "did not detect speech" in response.json()["detail"]
    assert not pitch_routes._transcription_lock.locked()


def test_local_whisper_consumes_segments_and_handles_bad_audio(monkeypatch) -> None:
    from types import SimpleNamespace
    import pytest

    class Model:
        def transcribe(self, audio, **options):
            assert audio.read() == b"recording"
            assert options == {"beam_size": 1, "vad_filter": True}
            return iter([SimpleNamespace(text=" Hello "), SimpleNamespace(text=" world. ")]), None

    monkeypatch.setattr(pitch_routes, "_whisper_model", lambda name: Model())
    assert pitch_routes._local_transcription(b"recording", "audio/webm") == "Hello world."
    with pytest.raises(RuntimeError, match="could not decode"):
        pitch_routes._local_transcription(b"invalid", "audio/webm")


def test_transcription_rejects_unknown_provider(monkeypatch) -> None:
    monkeypatch.setenv("ASR_PROVIDER", "typo")
    response = client.post(
        "/api/voice/transcribe", files={"file": ("question.wav", _wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 503
    assert "ASR_PROVIDER" in response.json()["detail"]
