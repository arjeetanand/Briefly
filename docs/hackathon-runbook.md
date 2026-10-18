# Pitchroom AI hackathon runbook

## The one-line pitch

**Pitchroom AI turns an approved pitch into a source-grounded voice conversation, so founders can rehearse hard questions without inventing answers.**

## The problem and audience

Founder-led teams use static decks to prepare for conversations that are not static. A surprise customer or investor question creates two bad outcomes: time lost searching slides, or a confident answer that the approved pitch never supported.

Pitchroom AI serves founders preparing for investor meetings, customer conversations, and internal demos. It is a rehearsal assistant, not an autonomous presenter or investor-research tool.

## What to claim

Say:

- “Pitchroom loads a pitch deck or document, keeps slide/page citations attached, listens after one start tap, and automatically sends a question after the speaker pauses.”
- “You can inspect the exact source sections that supported the answer.”
- “The refusal path is intentional. When Pitchroom finds no matching approved-source evidence, it says so.”
- “The current prototype provides seamless turn-taking, not streaming word-by-word transcription.”

Do not say:

- “It understands every chart, screenshot, or scanned slide automatically.”
- “It has multi-user storage, authentication, or production privacy controls.”
- “It provides real-time streaming conversation.”

## Two-minute presentation

### 0:00–0:20 — Hook

“Pitch decks are built to be read, but high-stakes meetings are conversations. The risky moment is the surprise question, when a founder searches slides or improvises an answer that was never approved.”

### 0:20–0:40 — Product

“Pitchroom AI turns the approved pitch into a voice rehearsal. The team loads the source, asks by voice, sees what the assistant heard, checks the supporting source text, and hears the answer back.”

### 0:40–1:40 — Live proof

1. Upload the real `.pptx` (or use `pitch.txt`) and say: “This is the approved source for the conversation.” Point out the slide count and any extraction warning before starting.
2. Select **Start live session** once and grant microphone permission.
3. Ask: “What problem does Pitchroom AI solve?” then stop speaking normally.
4. Point out that no record-stop action is needed: the pause sent the turn.
5. Point to **Heard**, the grounded answer, and **Source evidence**.
6. Let the spoken reply end and call out that the room is listening again. With `TTS_PROVIDER=kokoro`, say that the answer is being spoken by the local studio voice; otherwise it uses the free browser voice.
7. For a memorable live moment, speak over the reply with: “And what happens if there is no evidence?” Point out that the reply stops and the new question is captured without a second microphone click.

### 1:40–2:00 — Trust moment and close

Ask: “What is Pitchroom AI’s Series B valuation?”

“The approved source does not contain that fact. Pitchroom refuses instead of making it up. That is the behavior founders need before a high-stakes conversation.”

Close with: “Pitchroom AI helps a founder enter the room prepared, consistent, and able to keep every answer tied to the deck.”

## 30-second version

“Pitchroom AI turns an approved pitch into a source-grounded voice conversation. Upload a deck or document, ask a question aloud, see the slide/page evidence, and hear the reply. If the source does not support a claim, Pitchroom says so. Every answer, from the deck.”

## Stage preflight

Run this 10 minutes before judging:

1. Start the app and verify that `pitch.txt` appears as the approved source.
2. Select **Use demo brief** to reset the pitch.
3. Ask the first demo question by text and verify source evidence appears.
4. Start one live session in the browser you will present from.
5. If using Kokoro, open the room one minute early so its one-time local model load finishes; ask one short text question, then select **Play answer** to confirm the warm studio voice is ready.
6. Ask one short question, pause, and confirm the transcript, answer, source evidence, and spoken reply appear.
7. Confirm that listening resumes after the spoken reply.
8. Speak over a reply once and confirm the reply stops and the next question is captured.
9. Keep the text-demo questions ready as a fallback.

Use the included demo brief only for practice. Before using an actual company pitch, confirm that the configured transcription and speech providers may receive its content and recorded audio.

## Fallback plan

| If this happens | Do this |
| --- | --- |
| Microphone permission fails | Use a demo question by text and explain that the transcript plus answer path is identical after speech-to-text. |
| Venue audio is unreliable | Use headphones, choose `TTS_PROVIDER=browser`, or use **Play answer** if the browser permits it, then continue with the visible transcript and source evidence. |
| Kokoro is still loading | Use the free browser voice for that run, or wait for the first local warm-up before beginning the judged demo. |
| A provider is slow | Use the three scripted text questions, then show the source sections. |
| The question gets no match | Treat it as the trust moment. Say the source does not support the claim. |
| A real deck has image-only slides | Use the extraction warning as a trust moment, then keep a text-selectable PDF or short demo brief with the key facts written as clear sentences. |

## Next product steps

1. Add per-workspace storage and versioned sources.
2. Add OCR/vision extraction for image-only slides, charts, and scanned PDFs, with human-review flags.
3. Add per-answer confidence/calibration and a review queue for weak retrieval matches.
4. Add live streaming voice after the reliable recorded-turn workflow is proven.
