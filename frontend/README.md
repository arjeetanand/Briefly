# Pitchroom AI live-room frontend

`static/` is a no-build browser application served by FastAPI at `/`. It offers one-click work practice decks alongside manual file upload, grounded questions, and interruption-aware voice conversations.

The same static directory serves `/studio`, a separate owner workspace for
private assistants made from reviewed website pages and documents. It supports
typed questions, browser speech recognition and speech synthesis, source
citations, and optional publishing to a visitor link. The original `/` room
continues to use its existing continuous voice and interruption pipeline.

There is no separate Python frontend process; start the backend with the root
`./run-dev.sh` command and it serves this browser application and the API from
the same origin.

## Run

From the repository root:

```bash
./run-dev.sh
```

Open `http://127.0.0.1:8501`. Select a project update, customer success plan, team handbook, or onboarding deck, or upload a work document. The interface and API intentionally share one origin, including in production.

## Live voice behavior

1. The presenter selects **Start live session** once and grants microphone permission.
2. Browser VAD uses microphone RMS energy with a small adaptive noise floor.
3. Speech is confirmed after about 160 ms; a pause of about 850 ms ends the turn.
4. As the room opens, it calls `/api/voice/warm` and visibly reports **Studio voice ready**, browser-voice readiness, or fallback status. The endpoint is a no-op for browser and hosted voices, but preloads the explicitly selected local Kokoro studio voice before the first question.
5. The browser shows separate transcription and source-search states, then speaks the grounded answer through the configured server provider or directly through the built-in browser voice when `TTS_PROVIDER=browser` (the no-key default).
6. Before the short server WAV finishes buffering—and throughout playback—the browser retains a guarded hot capture. Sustained speech interrupts the reply and continues as the next question. Otherwise, the same microphone session re-arms automatically when playback ends.

An explicit **End live session** control stays available. A typed source-question form is the presentation fallback. The live loop needs an HTTPS page outside `localhost`; use Chrome or Edge for the most predictable demo behavior. Headphones are the most reliable setup for interruption because acoustic echo cancellation varies by venue and microphone.

The hero's **Try the live demo** control uses the same real grounded-answer endpoint without requesting the microphone. The first cited source appears beside the answer; the full source trail stays below.

## Visual layer

`static/spoken-page.css` contains the landing layout; the shared `static/theme.css` sets the voice-signal visual system across the landing page and Assistant Studio. The hero uses `assets/voice-answer-signal.png`; the line icons are Heroicons, with their MIT license in `assets/heroicons-LICENSE.txt`.

`static/motion.js` uses native requestAnimationFrame and IntersectionObserver for hero parallax, one-time reveals, and the sticky Ask / Hear / Know story. Its document, voice prompt, and cited answer layers travel at different rates as the active chapter changes. It only schedules work on scroll or resize; scrolling remains native. The generated ribbon gently floats with CSS animation. The former Three.js scene is no longer loaded by the page.

**Pause motion** stops decorative travel and expands the sticky story into normal flow. The system reduced-motion preference also disables travel and overrides that button. Small screens show all story chapters in a normal stack. Content remains visible if JavaScript or IntersectionObserver is unavailable, and hidden tabs pause the floating illustration.

The hero answer card is explicitly labeled as an illustrative example. The live demo, source picker, upload, transcript, and citations continue to use the existing backend.

Motion behavior checks: `node --test frontend/test_motion.mjs`.
