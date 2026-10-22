# Pitchroom AI

**Answers grounded in the material your team already uses.**

Pitchroom AI turns approved websites and documents into a source-grounded knowledge assistant. Ask by voice or text, hear a concise answer, and inspect the page, slide, or section behind it. A pitch is one use case alongside business FAQs, courses, proposals, and internal guides.

## The problem

People spend time looking up information they already have in project plans, proposals, policies, onboarding guides, and meeting decks. In a review or customer call, a missing detail can mean searching files or improvising an answer that was never approved.

Pitchroom AI gives people one place to ask questions about material they already trust. When it cannot find support in the approved sources, it says so instead of inventing a claim.

## What the prototype does

- Loads PPTX, PDF, DOCX, Markdown, and plain-text work material; OCRs scanned PDF pages and image-based PDF diagrams when Tesseract is installed.
- Preserves slide/page provenance, including PPTX speaker notes, and shows the
  citation beside each grounded answer.
- Shows recognized image text for review and warns that OCR may miss diagram
  arrows and branches; embedded DOCX/PPTX images are still warnings only.
- Retrieves the most relevant source sections for each question.
- Supports typed questions and one-tap live voice conversations.
- Runs hands-free turns: speech detected → pause detected → transcription → grounded answer → spoken reply → microphone re-armed.
- Stops a spoken reply when the presenter interrupts and treats the interruption as the next question.
- Shows the transcript, answer, and exact source sections used.
- Presents the demo in the approved ivory-and-plum Spoken Page design, with a floating voice illustration and an Ask / Hear / Know story that moves from source document to voice prompt to cited answer.
- Uses native scrolling and layered parallax, with a Pause motion control, reduced-motion support, and a stacked story on mobile.
- Includes starter sources for a consulting service guide, course lesson, customer plan, project update, team handbook, and new-starter guide, plus the original product brief.

The `/` live demo uses shared, fictional sample material stored in memory for that running API. Use `/studio` for persistent, owner-scoped assistants with your own sources and optional visitor links.

## Private assistant studio (pilot)

Open `/studio` to create a private assistant, add multiple supported files or a public website, review extracted passages and warnings, and approve only the sources it may use. Owners can return to saved assistants, rename or delete them, and ask by text or browser voice. Answers show excerpts and clickable website citations; unsupported questions receive an explicit refusal. Website imports stay on the submitted hostname, respect `robots.txt`, and stop at 100 pages, 25 MiB, or 45 seconds. Scanned PDFs are OCR'd when Tesseract is installed; verify diagram arrows and branches against the original. JavaScript-rendered pages and embedded images in DOCX/PPTX still need separate review. Website refresh is manual.

Assistants remain private until the owner publishes an approved source snapshot. The visitor link can be revoked; changes to sources do not silently alter an existing snapshot. Visitor feedback, unanswered counts, latency, and estimated embedding spend per browser conversation appear in the owner metrics. Cost estimates cover only embedding API tokens and use `OPENAI_EMBEDDING_USD_PER_MILLION_TOKENS`; hosting, browser speech, and other speech-provider charges are excluded.

Local data is stored in `backend/data/pitchroom.sqlite3` by default. Set `PITCHROOM_ACCESS_TOKEN` to require that code for both pilot registrations and the legacy room API. New accounts do not have email verification or password reset yet, so share the invite code only with pilot owners.

Keyword retrieval and extractive answers are local by default. To enable semantic retrieval, set `RETRIEVAL_PROVIDER=openai` and configure `OPENAI_API_KEY`; passages are sent once per content version for cached embeddings, and each question is sent for its query embedding. For plain-language explanations, explicitly set `ANSWER_GENERATION_PROVIDER=huggingface` with `HUGGINGFACE_API_TOKEN`; only retrieved excerpts and the question are sent to Hugging Face. These provider choices are disclosed in Studio.

## Run locally

The recommended local install includes CPU Whisper for transcription and Kokoro
for spoken replies. On first use it downloads the English `small.en` and Kokoro
models; after that, speech and document answers run on your computer without
hosted AI requests. Use `WHISPER_MODEL=small` for Whisper's multilingual model.
The Render deployment keeps browser voice and hosted Whisper as separate choices.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-kokoro.txt
cp .env.example .env
# macOS: brew install tesseract
# Debian/Ubuntu: sudo apt-get install tesseract-ocr
./run.sh
```

The Kokoro requirements are the recommended local install. They include the API,
local Whisper, and the studio voice. Install Tesseract separately to index text
in scanned PDF pages and diagrams. If you only need typed questions or browser
speech, install `backend/requirements.txt` instead and set `TTS_PROVIDER=browser`.

`./run.sh` uses port 4002 and safely restarts only its own server. The paired
test ports are 5002 and 6002 (`PORT=5002 ./run.sh` or `PORT=6002 ./run.sh`).
The existing `./run-dev.sh` command remains available on port 8501.

Open [http://127.0.0.1:4002](http://127.0.0.1:4002) for the live demo, or visit
[http://127.0.0.1:4002/studio](http://127.0.0.1:4002/studio) to create a private assistant.
Select a sample source or
upload your own approved PPTX, PDF, DOCX, Markdown, or TXT work file. Ask one of
the sample questions or type your own. The answer includes the supporting slide,
page, or section. Start a live session for spoken questions and replies. Legacy
binary `.ppt` files are converted only when LibreOffice is available; exporting
to `.pptx` is the reliable path.

Fictional starter sources are available to download and adapt:

- [Weekly project update](deliverables/demo-samples/weekly-project-update.pptx)
- [Customer success plan](deliverables/demo-samples/customer-success-plan.pptx)
- [Team handbook](deliverables/demo-samples/team-handbook.pptx)
- [New-starter guide](deliverables/demo-samples/new-starter-guide.pptx)
- [Course lesson guide](deliverables/demo-samples/course-lesson-guide.md)
- [Consulting service guide](deliverables/demo-samples/consulting-service-guide.md)

## Configuration

There is one configuration file: the repository-root `.env`. Start from the
categorized [`.env.example`](.env.example), copy it to `.env`, and change only
the values needed for your demo. The backend and deployment template use this
same configuration contract; there is no second backend or frontend env file.

For the local presentation voice, set:

```dotenv
TTS_PROVIDER=kokoro
KOKORO_LANG_CODE=a
KOKORO_VOICE=af_heart
KOKORO_SPEED=0.98
KOKORO_DEVICE=auto
```

Local microphone transcription uses Whisper on your computer. For hosted
transcription, choose `ASR_PROVIDER=huggingface` and add a Hugging Face token:

```dotenv
HUGGINGFACE_API_TOKEN=your_token_here
```

The hosted demo also requires a private `PITCHROOM_ACCESS_TOKEN` secret. Generate
one with `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`, then
add it to Render's environment settings. The legacy room asks attendees for
this token the first time they use the app in a tab; Assistant Studio uses the
same value as its pilot registration invite code. Set it in `.env` to enable the
access gate locally. The public `/health` check returns status only.

The important provider choices are:

- `TTS_PROVIDER=kokoro` is the recommended hackathon studio voice: a local, cached Kokoro English model with the curated `af_heart` narrator. Install it with `.venv/bin/python -m pip install -r backend/requirements-kokoro.txt`; its first model download is about 360 MB, then answer text stays on the presentation machine with no per-request TTS charge.
- `TTS_PROVIDER=auto` enables the configured server-provider chain; add `SARVAM_API_KEY` to include Sarvam Bulbul.
- `ASR_PROVIDER=local` uses on-device Whisper; `ASR_PROVIDER=huggingface` sends recordings to hosted Whisper.
- `ANSWER_GENERATION_PROVIDER=extractive` answers from the best matching source sections without a hosted language model. Set it to `huggingface` only for hosted answer generation.
- `OPENAI_API_KEY` enables the OpenAI text-to-speech fallback.
- `TTS_PROVIDER=browser` forces the free browser-native voice; it needs no API key and keeps reply text in the browser.
- `TTS_PROVIDER=piper` plus `PIPER_TTS_URL` uses a free local Piper neural voice. Setup commands are in [backend/README.md](backend/README.md).

The remaining provider settings are grouped in `.env.example` under runtime,
speech-to-text, local voice, and hosted voice sections. You do not need to fill
every key. Typed questions and both local voice models work without a provider key.

Kokoro starts warming as the live room opens, loading its model and narrator while the presenter gets ready. On its first install it downloads the public model artifacts from Hugging Face (not your answer text); after that cache is present, answers stay on the presentation machine and the demo can run offline for TTS. For the first launch, wait until the page is fully open before the first question; later answers use the in-memory model. This avoids a provider round trip, but it is not literal streaming audio—keep live answers to one to three sentences for the quickest response. Use `KOKORO_VOICE=af_bella` to audition the alternative high-quality English narrator, then keep one voice consistent for the demo.

Pitchroom uses deterministic extractive answers by default, which makes the demo fast and auditable. Set `ANSWER_GENERATION_PROVIDER=huggingface` only after testing the configured hosted model. `MAX_AUDIO_BYTES` defaults to 10 MiB. In `auto` mode, configured server speech providers are tried before the browser voice fallback; `browser` is the safest no-cost demo setting. Kokoro is explicit-only and never silently enters that chain.

Voice requests send recorded audio and, when a hosted server TTS provider is selected, reply text to those configured third-party providers. With `TTS_PROVIDER=browser` or `TTS_PROVIDER=kokoro`, reply text is synthesized locally. The live transcription path still uses the configured speech-to-text provider. Use only a non-sensitive demo brief unless your organization has approved that data handling.

The live microphone session needs a current desktop browser and HTTPS in
deployment (`localhost` is permitted for local development). Chrome or Edge is
the recommended presentation browser. Headphones are the most reliable setup
for interruption because acoustic echo cancellation varies by venue.

## MCP plugin demo

Pitchroom also exposes a read-only MCP tool, `ask_pitch`, over Streamable HTTP
at `/mcp/`. It uses the bundled synthetic `backend/data/pitch.txt` brief, returns
matching citations, and declines unsupported questions. It never reads the
browser room's active upload, so the endpoint does not expose a presenter's
document. The endpoint is intentionally unauthenticated and safe only because
it is restricted to this public demo brief.

With the local server running, an MCP client can connect to
`http://127.0.0.1:4002/mcp/`. For a remote ChatGPT/MCP connection, use the HTTPS
deployment endpoint `https://pitchvoice-ai.onrender.com/mcp/` after that
deployment has the MCP changes; ChatGPT cannot reach a local `127.0.0.1`
server. Connecting a remote endpoint may require enabling developer mode in
ChatGPT.

The end-to-end protocol test runs with:

```bash
.venv/bin/python -m pytest backend/test_mcp.py -q
```

## Repository layout

| Path | Purpose |
| --- | --- |
| `frontend/static/` | The Spoken Page browser UI, native scroll motion, VAD, barge-in handling, transcript, and source-evidence UI. |
| `backend/app.py` | FastAPI entrypoint; serves the browser room and `/api` from one origin. |
| `backend/routes/pitch.py` | Document ingestion, grounded answers, transcription, and speech-provider integrations. |
| `backend/routes/assistants.py` | Persistent owner-scoped assistants, public-site import, source approval, sharing, and pilot metrics. |
| `frontend/static/studio.*` | Private assistant studio and public visitor-link experience. |
| `backend/config.py` | Loads the root `.env` and owns the supported setting names and defaults. |
| `backend/data/pitch.txt` | Verified demo brief used by **Use demo brief**. |
| `run.sh` | Restart-safe local server on port 4002 (test ports 5002 and 6002). |
| `run-dev.sh` | Local development server on port 8501. |
| `render-start.sh` | Render production start command. |

## Hackathon demo sequence

1. Start with the problem: static decks do not answer live questions.
2. Upload the real `.pptx` when the deck is text-selectable, then point to the
   visible slide/page extraction status. Use **Use demo brief** if needed.
3. Start the live session once and say: “What problem does Pitchroom AI solve?”
4. Pause; point out that the turn sends automatically, with no record-stop control.
5. Point to **Heard**, the grounded answer, the exact source evidence, and the spoken reply.
6. Ask an unsupported question, such as “What is the Series B valuation?” Explain that refusal is the trust feature.

For a real judging demo, keep a text-selectable deck or exported PDF ready. A
slide that is only a screenshot or chart is surfaced as a review warning; it is
not silently treated as reliable evidence.

The full speaking script and fallback plan are in [docs/hackathon-runbook.md](docs/hackathon-runbook.md).
The format support, trust boundary, and production path are in
[presentation-product-plan.md](presentation-product-plan.md).

## Testing

```bash
.venv/bin/python -m pytest backend -q
node --check frontend/static/app.js
node --check frontend/static/motion.js
node --check frontend/static/studio.js
node --test frontend/test_motion.mjs
node --test frontend/test_e2e.mjs # local Chrome required
```

## Deployment

The fixed Cloudflare demo link is [pitchroom-gateway.arjeet-anand2024.workers.dev](https://pitchroom-gateway.arjeet-anand2024.workers.dev).
When a quick tunnel restarts, update the gateway's `BACKEND_URL`; the public link
stays the same. See [the gateway setup and update instructions](cloudflare/README.md).
The local Python app and tunnel must remain running.

`render.yaml` exposes one FastAPI service that serves both the static live room
and `/api` from the same public origin. Render uses the free browser voice by
default, so only `HUGGINGFACE_API_TOKEN` is needed for live speech. Run Kokoro
locally for the polished in-person presentation voice, or configure another
server provider only when you intentionally need it. HTTPS is required for
microphone capture outside local development.

Before presenting from a deployed service, use a non-sensitive source document, run the microphone check in the target browser, make one automatic-pause voice turn, and verify that a spoken interruption starts a fresh turn.

The included Render free service has ephemeral storage, so its SQLite accounts,
sources, sessions, and share snapshots can disappear on restart or redeploy.
Use a persistent disk or managed database before inviting hosted pilot owners;
the current free deployment is suitable for demos, not durable pilot data.



cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8502
