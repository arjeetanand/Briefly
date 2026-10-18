# Pitchroom AI backend

FastAPI service for the legacy voice rehearsal room and private assistants grounded in owner-approved sources.

## Assistant studio

The `/studio` interface adds private, owner-scoped assistants alongside the
legacy shared rehearsal room. Owners can save assistants, upload supported
documents, import same-domain public website pages, review and approve sources,
ask with text or browser voice, and optionally publish a revocable link to an
immutable source snapshot. Grounded replies use the instance's configured
speech provider, including the same Kokoro voice as the live room when selected;
each answer also has a replay control. `backend/routes/assistants.py` owns the SQLite
accounts, sessions, source versions, visitor links, feedback, and usage metrics.

`PITCHROOM_DATABASE_PATH` defaults to `backend/data/pitchroom.sqlite3`.
`PITCHROOM_ACCESS_TOKEN`, when set, is also the pilot registration invite code.
Semantic retrieval is opt-in with `RETRIEVAL_PROVIDER=openai` and
`OPENAI_API_KEY`; it sends source passages and query text to the configured
embedding API. Set `OPENAI_EMBEDDING_USD_PER_MILLION_TOKENS` to the correct
input rate for the selected model. The cost metric is an estimate for embedding
usage only and excludes hosting and speech providers. New pilot accounts do
not yet have email verification or password recovery.

The provided Render free deployment uses ephemeral storage. Configure a
persistent disk or external database before using it for durable pilot accounts
and source content.

Assistant API routes:

- `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`,
  and `GET /api/auth/me` manage pilot accounts and sessions.
- `/api/assistants` provides owner-scoped create, list, rename, reopen, and
  delete operations.
- `/api/assistants/{id}/sources/files` uploads supported documents;
  `/sources/websites` imports same-host public pages. New or changed sources
  require explicit approval through `/sources/{source_id}`.
- `/api/assistants/{id}/answer`, `/feedback`, and `/metrics` handle private
  Q&A and pilot signals. `POST /publish` creates a visitor snapshot and
  `DELETE /publish` revokes its link.
- `/api/shared/{token}` serves the visitor snapshot and its Q&A/feedback routes.
- `/api/assistants/{id}/voice/warm` and `/api/shared/{token}/voice/warm` warm
  the selected provider within the owner's or published-link access boundary.
- `/api/assistants/{id}/answers/{answer_id}/speech` and the corresponding
  `/api/shared/{token}/answers/{answer_id}/speech` route speak only grounded
  answers, with a 280-character limit and 12 spoken replies per assistant per
  minute. If `TTS_PROVIDER=browser`, the routes
  return `409` so the client uses the browser voice; configured server-provider
  failures remain visible instead of silently switching narrators.

## Run locally

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload
```

For local MMS TTS, the requirements install a CPU-only PyTorch build on Linux and a compatible PyPI wheel on macOS/other local platforms:

```bash
python -m pip install -r requirements.txt
```

The API runs at `http://localhost:8000` when launched directly. The repository's `./run-dev.sh` starts the same FastAPI app at `http://127.0.0.1:8501` and also serves the presentation-ready live browser room at `/`. Interactive API documentation is available at `/docs`.

## Routes

- `GET /health` checks service and document state.
- `GET /api/pitch` returns the loaded pitch, source sections, citations, and extraction metadata.
- `POST /api/pitch/demo` restores the included Pitchroom demo brief.
- `GET /api/pitch/samples` lists the four fictional work scenarios available in the live room.
- `POST /api/pitch/sample/{sample_id}` loads a bundled sample source using the same document extraction and citation pipeline as a user upload.
- `POST /api/pitch/document` accepts `{ "document": "..." }`.
- `POST /api/pitch/file` accepts PPTX, PDF, DOCX, plain-text, or Markdown uploads. PPTX text and speaker notes are extracted slide by slide; PDF text is extracted page by page with PyMuPDF and image text is OCR'd with Tesseract when available; DOCX paragraphs are extracted from OOXML. OCR preserves page citations and warns that diagram arrows and branches need visual review. Legacy `.ppt` files use LibreOffice when it is installed.
- `POST /api/voice/answer` accepts `{ "question": "..." }` and returns the full grounded `answer`, a concise `spoken_answer` for playback, source chunks, and `source_refs` such as `Slide 4` or `Page 2`. The spoken version uses at most two complete sentences and 280 characters; the full answer and evidence remain visible.
- `POST /api/pitch/read` returns audio for the loaded pitch. Kokoro, Sarvam, Piper, local Hugging Face, and Hugging Face API output WAV; OpenAI output is MP3.
- `POST /api/voice/speak` accepts `{ "text": "...", "voice": "alloy" }` and returns audio with the correct `Content-Type`.
- `POST /api/voice/warm` warms the explicitly selected local Kokoro voice without invoking any hosted provider. The browser room calls this on load.
- `POST /api/voice/transcribe` accepts a supported recorded audio file up to `MAX_AUDIO_BYTES` and returns a Whisper transcription from the selected `ASR_PROVIDER` (`local` or `huggingface`).

## Recommended local studio voice: Kokoro

Kokoro is the presentation-quality local English path. It uses the fixed official Apache-2.0 `hexgrad/Kokoro-82M` model, keeps answer text on the machine after its first download, and is selected only when `TTS_PROVIDER=kokoro` is set. It does not replace the browser fallback or call Sarvam.

```bash
python -m pip install -r requirements-kokoro.txt
# Optional but recommended for uncommon names and acronyms:
# macOS: brew install espeak-ng
# Ubuntu/Debian: sudo apt-get install espeak-ng
```

Set the following in the repository-root `.env`, then start the real FastAPI process before presenting:

```dotenv
TTS_PROVIDER=kokoro
KOKORO_LANG_CODE=a
KOKORO_VOICE=af_heart
KOKORO_SPEED=0.98
KOKORO_DEVICE=auto
```

The page asks `/api/voice/warm` to load the model and a short test phrase as soon as it opens, and repeated page loads return immediately once that server process is warm. The initial artifact download contacts Hugging Face but does not contain answer text; pre-cache it before an offline presentation. Wait for that first load (roughly 360 MB is cached locally), then run one text question and select **Play answer** before presenting. `af_bella` is the practical alternate narrator to audition. The full answer retains complete sentences up to 1,000 characters; Kokoro reads the concise `spoken_answer` while the full evidence stays visible. Synthesis keeps a separate 1,200-character hard guard. The browser buffers one WAV response rather than word-by-word streaming.

For this demo, use the curated pretrained narrator instead of a custom fine-tune. Fine-tuning needs a licensed, consented voice dataset plus evaluation time, and it does not remove model warm-up or response-generation latency.

For a smaller local neural fallback, run Piper and point `PIPER_TTS_URL` at it:

```bash
python -m pip install "piper-tts[http]"
python -m piper.download_voices en_US-lessac-medium
python -m piper.http_server -m en_US-lessac-medium --host 127.0.0.1 --port 5000
```

Then set `TTS_PROVIDER=piper` and `PIPER_TTS_URL=http://127.0.0.1:5000/synthesize`. Piper is local and does not require a provider key; voice models have their own licenses, so check the selected model before shipping.

Set `TTS_PROVIDER=auto` with `SARVAM_API_KEY` to use Sarvam Bulbul for speech output. In `auto` mode, Sarvam is tried first, then configured local Piper, Hugging Face, or OpenAI providers. Kokoro is intentionally excluded from `auto`, so the model is never downloaded unless it is explicitly chosen. The default `TTS_PROVIDER=browser` keeps the demo free: the shipped browser room uses its built-in SpeechSynthesis voice when no server TTS is selected, so a presentation can speak without Sarvam. Speech-to-text defaults to hosted Hugging Face Whisper. For local CPU transcription, install `requirements-whisper.txt` and set `ASR_PROVIDER=local` with `WHISPER_MODEL=base.en`; no API token is needed and the model downloads once. Source-grounded extractive answers are the default; set `ANSWER_GENERATION_PROVIDER=huggingface` only to opt into hosted answer generation. Without provider keys, extractive Q&A still works and the browser handles reply speech locally.

The repository-root `.env` is loaded automatically when the backend starts.
Use the categorized root [`.env.example`](../.env.example) as the only setup
reference. For hosted transcription, fill in `HUGGINGFACE_API_TOKEN` before using microphone
transcription. `FRONTEND_ORIGINS` is only needed if a separate frontend origin
will call the API; the shipped live room uses the same origin. Use a
non-sensitive demo source because configured providers receive audio and text
needed to process a voice turn.

Document ingestion is intentionally honest: scanned PDF pages and image-heavy
PDF pages are OCR'd when Tesseract is installed, with page citations and a
warning to verify diagram layout and arrows. If Tesseract is unavailable, the
source warning identifies image pages that could not be indexed. Embedded
images in PPTX and DOCX are still counted and returned as review warnings.
OCR extracts text labels; it does not prove arbitrary visual relationships.

## Tests

```powershell
python -m pytest -q
```
