# Architecture

Pitchroom AI serves one same-origin browser application from FastAPI. This is deliberate: the live browser microphone can send its audio to `/api` without trying to reach a private server address from a presentation attendee's device.

```text
Browser live room (frontend/static)
        |
        +-- MediaRecorder + adaptive silence detection
        |       Start once → speak → pause → send turn
        |
        | same-origin /api
        v
FastAPI (backend/)
        |
        +-- document extraction and in-memory source store
        +-- source-grounded Q&A
        +-- speech-to-text and text-to-speech providers
```

## Components

| Area | Responsibility |
| --- | --- |
| `frontend/static/` | Light presentation interface, shader-backed 3D particle field, browser microphone lifecycle, adaptive silence detection, source evidence, typed fallback, and audio playback. |
| `backend/config.py` | Loads the single repository-root `.env` and owns the supported setting names and safe defaults. |
| `backend/routes/pitch.py` | Extracts document content, preserves slide/page provenance, selects relevant source chunks, and provides Q&A and audio endpoints. |
| `backend/data/pitch.txt` | Verified demo brief used by the one-click demo path. |
| `run-dev.sh` | Starts the same-origin FastAPI application on port 8501 by default. |
| `render-start.sh` | Starts one public FastAPI process on Render's assigned port. |

## Request flow

1. The user loads the included demo brief or uploads a pitch document in the browser interface.
2. The API identifies the format and extracts selectable text into citable sections: slides and speaker notes for PPTX, pages for PDF, and paragraphs for DOCX. It returns extraction warnings when image-only material was not understood.
3. For each question, the API selects relevant sections with lexical and lightweight stem matching, then returns a deterministic extractive answer plus slide/page citations by default. Hugging Face answer generation is an explicit optional enhancement.
4. During a live session, the browser begins recording once speech is confirmed and ends a turn after about 850 ms of silence. It sends WebM or MP4 audio to Hugging Face Whisper, retrieves source sections, synthesizes the answer through configured local Kokoro, Sarvam, local Piper, Hugging Face, or OpenAI providers, then re-arms the same microphone stream after reply playback. If no server TTS is available, the browser uses its built-in SpeechSynthesis voice locally. A guarded hot capture starts before the short speech response finishes buffering, so sustained speech before or during a reply cancels playback and becomes the next turn.

## Operational notes

- API credentials live only in the root `.env` file or deployment secret environment variables; supported names and defaults are documented in the root `.env.example` and `backend/config.py`.
- The active document is in-memory; it resets when the API restarts. Persistent per-user document storage is a future extension.
- The source text and recorded audio leave the app when a configured third-party transcription or speech provider processes them. Use an approved non-sensitive demo source.
- Set `TTS_PROVIDER=browser` for a no-key presentation: reply text stays in the browser and is spoken by the device voice. Set `TTS_PROVIDER=kokoro` for the preferred local 24 kHz English studio voice; the FastAPI process caches its fixed official model and selected narrator after the page warms it. Kokoro is bounded to short live replies so a document read cannot monopolize the local model. Set `TTS_PROVIDER=piper` with `PIPER_TTS_URL` for a smaller local neural fallback; Piper is an optional separate process.
- Browser microphone capture requires HTTPS in deployment (or `localhost` while developing). There is intentionally one explicit **Start live session** control because browsers require a user gesture for microphone permission.
- Text extraction supports PPTX/DOCX selectable text, PPTX speaker notes, selectable PDF text, and plain text/Markdown. Image-only slides, scanned pages, and chart screenshots are surfaced as warnings; OCR/vision extraction is the next step before treating those claims as searchable evidence.
- The generated orb is a local presentation asset; its animation is decorative and independent from the silence-detection loop. Reduced-motion settings disable its motion.
