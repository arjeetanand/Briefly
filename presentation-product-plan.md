# Pitchroom AI — presentation-ready product plan

## Verdict

The current build is strong enough for a controlled hackathon demo, but it is
not yet a universal “ask anything from any file” product.

It now handles:

- PPTX slide text and speaker notes, with `Slide N` citations.
- Selectable PDF text, with `Page N` citations.
- DOCX paragraphs, with document-section citations.
- Markdown and plain-text briefs.
- Automatic voice turns, interruption-aware playback, grounded answers, and a
  typed fallback.

It deliberately flags rather than invents answers for image-only slides,
scanned pages, screenshots, and chart-only visuals. Legacy `.ppt` conversion is
available only when LibreOffice is installed; `.pptx` is the reliable upload
format.

## The product promise

**Upload the approved pitch. Ask the hard question. Hear a concise answer and
see exactly where it came from.**

The trust feature is the boundary: when the source does not support a claim,
Pitchroom declines. “Works with everything” should mean “accepts the common
formats and clearly reports what it could and could not understand,” not
“hallucinates a response from a chart it never read.”

## Three-tier source support

| Tier | Source material | Product behavior | Presentation language |
| --- | --- | --- | --- |
| A — grounded | PPTX/PDF/DOCX selectable text, tables, notes, Markdown, TXT | Searchable, citable, answerable | “Pitchroom answers from the approved text and shows the slide/page.” |
| B — extracted with review | OCR text from scanned pages or slide images | Searchable, but visibly marked for review | “Pitchroom found text, and the presenter can verify the visual.” |
| C — unsupported visual claim | Complex charts, diagrams, screenshots, handwriting, uncaptured audio/video | Warning plus typed/manual review path; no confident answer | “This claim needs human verification; Pitchroom will not guess.” |

## The ideal judging flow

1. **Preflight** — Upload the real deck. Show format, slide count, source
   readiness, warning count, microphone readiness, and voice readiness.
2. **Source proof** — Open the extracted source panel. The presenter can point
   to `Slide 4` or `Page 7` before asking anything.
3. **One-tap room** — Start the microphone once. The presenter speaks
   naturally; a short pause submits the turn.
4. **Evidence answer** — Show the heard question, concise spoken answer,
   matching excerpts, and citations in the same viewport.
5. **Trust boundary** — Ask an unsupported question. The answer declines and
   explains that the source contains no supporting evidence.
6. **Recovery** — If microphone, model, network, or audio fails, the typed
   question and Play answer controls remain usable without resetting the source.

## Architecture needed for a durable product

### 1. Ingestion envelope

Normalize every upload into a versioned source package:

```text
SourcePackage
  id, filename, format, created_at, checksum
  sections[]
    id, text, citation, slide/page, title, notes, modality
  assets[]
    image/chart reference, OCR status, review status
  warnings[]
```

The current `DocumentStore` implements the first useful slice of this envelope
in memory. The next production step is a persisted, per-workspace version so a
new upload cannot overwrite another presenter’s source.

### 2. Hybrid retrieval

Keep the deterministic lexical path as the safety floor, then add:

- exact and stemmed keyword scoring;
- title/heading boosts;
- slide/page metadata filters;
- embeddings for paraphrases such as “runway” vs “months of cash left”;
- a minimum evidence threshold and an explicit “not enough support” state.

Every answer should carry the section IDs used to produce it. Generated prose
may improve fluency, but it must never remove citations or bypass the threshold.

### 3. Visual understanding

Add OCR only where it helps, and keep the result marked as OCR. For charts and
diagrams, extract the chart title, axes, legend, and visible labels before
attempting a vision answer. A review queue should show the captured image next
to the extracted claim. The system should never present an inferred trend as a
source quote.

### 4. Presentation reliability

Before the first live turn, run a 20-second local check:

- source loaded and warnings acknowledged;
- one known answer returned under a latency budget;
- microphone permission granted;
- transcription provider reachable;
- local Kokoro warmed or browser fallback selected;
- one interruption test passed;
- typed fallback visible.

Cache the source index and warmed voice. Keep the active source immutable during
the live session. If the presenter changes the source, require a clear “Start
new rehearsal” action so evidence never mixes across versions.

## What to measure before calling it ready

Create a small evaluation set from each deck:

- 10 questions answered directly by one slide/page;
- 5 paraphrased questions;
- 5 cross-slide questions;
- 5 unsupported questions;
- 3 visual-only questions that must produce a review warning.

Track retrieval hit@3, unsupported precision, citation accuracy, answer length,
first-audio latency, interruption-to-listening latency, and failure recovery.
For a hackathon demo, the visible target is simple: every known question shows
the correct citation, every unsupported question declines, and the presenter
can recover without a page reload.

## Recommended build order

### Now — hackathon safe

- Use the updated PPTX/PDF/DOCX ingestion and show the extraction warning.
- Keep a text-selectable deck and the included demo brief as fallbacks.
- Warm Kokoro before the judges arrive; keep browser voice available.
- Rehearse one known question, one interruption, and one unsupported question.

### Next — product credibility

- Persist workspaces and source versions.
- Add hybrid embedding retrieval and answer confidence.
- Add OCR for scanned pages and slide images, with review labels.
- Add chart/diagram extraction with a human-verification state.

### Later — platform

- Streaming ASR/TTS after the recorded-turn path is measured and stable.
- Multi-user auth, encrypted storage, retention controls, and audit logs.
- Evaluation dashboards showing citation accuracy and unsupported-answer rate.

## The pitch to judges

“Pitchroom turns an approved deck into a live rehearsal room. Upload a PPTX,
ask a question naturally, and the answer comes back with the exact slide or page
that supports it. If the deck does not contain the claim, Pitchroom says so.
The product is not trying to sound confident about unknown information; it is
trying to keep a founder consistent and prepared in the moment that matters.”
