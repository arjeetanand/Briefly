/* Pitchroom AI's live room runs entirely in the browser after one explicit
 * microphone permission.  The recording is started while the room is armed;
 * adaptive RMS VAD decides when a speaker has finished a turn. */

const END_OF_TURN_MS = 850;
const SPEECH_CONFIRMATION_MS = 160;
const BARGE_IN_CONFIRMATION_MS = 280;
const BARGE_IN_GRACE_MS = 360;
const BARGE_IN_MIN_THRESHOLD = 0.018;
const BARGE_IN_THRESHOLD_MULTIPLIER = 1.45;
const BARGE_PREARM_MAX_MS = 4000;
const MAX_TURN_MS = 25000;
const CALIBRATION_MS = 850;
const MIN_VOICE_THRESHOLD = 0.012;
const MAX_VOICE_THRESHOLD = 0.06;

const elements = {
  stage: document.querySelector("#stage-card"),
  stateLabel: document.querySelector("#state-label"),
  stageTitle: document.querySelector("#stage-message-title"),
  stageCopy: document.querySelector("#stage-message-copy"),
  liveToggles: [...document.querySelectorAll("[data-live-session-toggle]")],
  liveToggleLabels: [...document.querySelectorAll("[data-live-session-toggle] span[data-idle-label]")],
  liveHint: document.querySelector("#live-hint"),
  voiceReadiness: document.querySelector("#voice-readiness"),
  liveAnnouncement: document.querySelector("#live-announcement"),
  voiceError: document.querySelector("#voice-error"),
  agentTraceStatus: document.querySelector("#agent-trace-status"),
  heroAgentState: document.querySelector("#hero-agent-state"),
  heroSourceStatus: document.querySelector("#hero-source-status"),
  heroConsoleReady: document.querySelector(".hero-console-ready"),
  sourcePeek: document.querySelector("#source-peek"),
  sourcePeekCitation: document.querySelector("#source-peek-citation"),
  sourcePeekText: document.querySelector("#source-peek-text"),
  heard: document.querySelector("#heard-question"),
  answer: document.querySelector("#answer-copy"),
  groundingBadge: document.querySelector("#grounding-badge"),
  evidenceStatus: document.querySelector("#evidence-status"),
  evidenceList: document.querySelector("#evidence-list"),
  sourceNameTop: document.querySelector("#source-name-top"),
  sourceMeta: document.querySelector("#source-meta"),
  sourceIngestStatus: document.querySelector("#source-ingest-status"),
  sourceExcerpt: document.querySelector("#source-excerpt"),
  sampleList: document.querySelector("#sample-list"),
  demoReset: document.querySelector("#demo-reset"),
  demoResetSource: document.querySelector("#demo-reset-source"),
  textQuestionForm: document.querySelector("#text-question-form"),
  textQuestion: document.querySelector("#text-question"),
  askButton: document.querySelector('#text-question-form button[type="submit"]'),
  playAnswer: document.querySelector("#play-answer"),
  flowHeard: document.querySelector("#flow-heard"),
  flowSource: document.querySelector("#flow-source"),
  flowAnswer: document.querySelector("#flow-answer"),
  meterBars: [...document.querySelectorAll(".voice-meter span")],
  questionPrompts: [...document.querySelectorAll("[data-question]")],
};

const state = {
  active: false,
  phase: "ready",
  sessionId: 0,
  stream: null,
  audioContext: null,
  analyser: null,
  analyserData: null,
  meterFrame: null,
  recorder: null,
  recorderContext: null,
  captureId: 0,
  recorderStartedAt: 0,
  turnStartedAt: 0,
  speechCandidateAt: 0,
  silenceStartedAt: 0,
  hasSpoken: false,
  calibrationUntil: 0,
  noiseFloor: 0.003,
  voiceThreshold: MIN_VOICE_THRESHOLD,
  currentAudio: null,
  currentAudioUrl: null,
  playbackId: 0,
  currentSpeech: null,
  browserSpeechId: 0,
  browserSpeechCancel: null,
  speakingStartedAt: 0,
  bargeCandidateAt: 0,
  bargeInArmed: false,
  turnEpoch: 0,
  lastAnswer: "",
  lastSpokenAnswer: "",
  pendingAbort: null,
  typedAbort: null,
  sourceSwitching: false,
  speechWarmPromise: null,
  speechProvider: null,
  samples: [],
  selectedSample: null,
};

const phaseCopy = {
  ready: {
    label: "Ready when you are",
    title: "One tap starts the room.",
    copy: "Pitchroom automatically closes each turn after a brief pause, answers from the source, and re-arms the microphone.",
    hint: "Your browser will ask once for microphone permission.",
  },
  arming: {
    label: "Opening microphone",
    title: "Getting the room ready.",
    copy: "Allow microphone access in your browser to begin the live voice session.",
    hint: "This only happens once per session.",
  },
  listening: {
    label: "Listening",
    title: "Speak naturally. Pause when you are finished.",
    copy: "Pitchroom detects the end of your question after a short pause—there is no stop button for each turn.",
    hint: "Live microphone · end session at any time",
  },
  transcribing: {
    label: "Transcribing",
    title: "Turning your question into text.",
    copy: "Pitchroom is checking what it heard before searching the approved source.",
    hint: "Your next turn will re-arm automatically.",
  },
  thinking: {
    label: "Finding source evidence",
    title: "Checking the approved source.",
    copy: "Pitchroom is finding the strongest supporting sentences before it responds.",
    hint: "Your next turn will re-arm automatically.",
  },
  speaking: {
    label: "Answering aloud",
    title: "Pitchroom is answering.",
    copy: "Speak over the reply to interrupt it. Pitchroom will stop and listen to your new question.",
    hint: "Listening resumes after the reply or your interruption.",
  },
  error: {
    label: "Needs attention",
    title: "The live room needs a quick reset.",
    copy: "You can keep using typed questions, or start a new live session after checking microphone and voice-provider setup.",
    hint: "Typed source questions remain available below.",
  },
};

function setPhase(phase, announcement = "") {
  state.phase = phase;
  elements.stage.className = `stage-card is-${phase}`;
  document.documentElement.dataset.voicePhase = phase;
  window.PitchroomScene?.setPhase?.(phase);
  window.dispatchEvent(new CustomEvent("pitchroom:voice-phase", { detail: { phase } }));
  const copy = phaseCopy[phase] || phaseCopy.ready;
  elements.stateLabel.textContent = copy.label;
  elements.stageTitle.textContent = copy.title;
  elements.stageCopy.textContent = copy.copy;
  elements.liveHint.textContent = copy.hint;
  if (elements.agentTraceStatus) elements.agentTraceStatus.textContent = copy.label;
  if (elements.heroAgentState) elements.heroAgentState.textContent = copy.label;
  const isActive = state.active;
  const buttonText = isActive ? "End live session" : "Start live session";
  elements.liveToggleLabels.forEach((label) => {
    label.textContent = isActive ? buttonText : (label.dataset.idleLabel || buttonText);
  });
  elements.liveToggles.forEach((toggle) => {
    toggle.setAttribute("aria-pressed", String(isActive));
    toggle.setAttribute("aria-label", isActive ? "End live session" : (toggle.querySelector("[data-idle-label]")?.dataset.idleLabel || buttonText));
  });
  if (announcement) elements.liveAnnouncement.textContent = announcement;
  updateFlow();
}

function updateFlow() {
  const inNewTurn = state.phase === "transcribing" || state.phase === "thinking" || (state.phase === "listening" && state.hasSpoken);
  const current = state.phase === "thinking" ? 2 : state.phase === "speaking" || (!inNewTurn && state.lastAnswer) ? 3 : 1;
  const steps = [elements.flowHeard, elements.flowSource, elements.flowAnswer];
  steps.forEach((step, index) => {
    step.classList.toggle("is-current", index + 1 === current);
    step.classList.toggle("is-complete", index + 1 < current || (index + 1 === 3 && Boolean(state.lastAnswer) && !inNewTurn));
  });
}

function showError(message, keepSession = false) {
  elements.voiceError.textContent = message;
  elements.voiceError.hidden = false;
  if (!keepSession) setPhase("error", message);
}

function clearError() {
  elements.voiceError.hidden = true;
  elements.voiceError.textContent = "";
}

function setSourceSwitching(switching) {
  state.sourceSwitching = switching;
  elements.askButton.disabled = switching || Boolean(state.typedAbort);
  elements.liveToggles.forEach((toggle) => { toggle.disabled = switching; });
  elements.questionPrompts.forEach((prompt) => { prompt.disabled = switching; });
  elements.demoReset.disabled = switching;
  elements.demoResetSource.disabled = switching;
  elements.sampleList?.querySelectorAll("button").forEach((button) => { button.disabled = switching; });
}

function responseDetail(payload, fallback) {
  if (payload && typeof payload === "object" && payload.detail) return String(payload.detail);
  return fallback;
}

async function getJson(path, options = {}) {
  const response = await apiFetch(path, {
    ...options,
    headers: { Accept: "application/json", ...(options.headers || {}) },
  });
  let body = null;
  try { body = await response.json(); } catch (_) { /* keep the HTTP error readable below */ }
  if (!response.ok) throw new Error(responseDetail(body, `Request failed (${response.status}).`));
  return body;
}

const ROOM_TOKEN_KEY = "pitchroom_access_token";
let roomTokenPrompt = null;
let roomTokenInMemory = "";

function storedRoomToken() {
  try { return sessionStorage.getItem(ROOM_TOKEN_KEY) || roomTokenInMemory; } catch (_) { return roomTokenInMemory; }
}

function saveRoomToken(token) {
  roomTokenInMemory = token;
  try {
    if (token) sessionStorage.setItem(ROOM_TOKEN_KEY, token);
    else sessionStorage.removeItem(ROOM_TOKEN_KEY);
  } catch (_) { /* retain this tab's token in memory */ }
}

function promptForRoomToken() {
  if (!roomTokenPrompt) {
    roomTokenPrompt = Promise.resolve(window.prompt("Enter the access token configured for this Pitchroom room."))
      .then((token) => (token || "").trim())
      .finally(() => { roomTokenPrompt = null; });
  }
  return roomTokenPrompt;
}

async function apiFetch(path, options = {}) {
  const send = () => {
    const headers = new Headers(options.headers || {});
    const token = storedRoomToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return fetch(path, { ...options, headers });
  };

  let response = await send();
  if (response.status !== 401) return response;
  const token = await promptForRoomToken();
  if (!token) return response;
  saveRoomToken(token);
  response = await send();
  if (response.status === 401) saveRoomToken("");
  return response;
}

function setAnswerPlaceholder() {
  state.lastAnswer = "";
  state.lastSpokenAnswer = "";
  elements.answer.textContent = "Pitchroom will answer only when it finds matching approved-source evidence.";
  elements.answer.classList.add("placeholder");
  elements.groundingBadge.textContent = "Waiting for a question";
  elements.groundingBadge.className = "grounding-badge";
  elements.playAnswer.hidden = true;
  elements.evidenceStatus.textContent = "Load a question to see the exact source section used.";
  elements.evidenceList.innerHTML = '<p class="empty-evidence">No answer yet. Pitchroom will show the source sentences behind each grounded response.</p>';
  if (elements.sourcePeek) elements.sourcePeek.hidden = true;
  if (elements.sourcePeekCitation) elements.sourcePeekCitation.textContent = "";
  if (elements.sourcePeekText) elements.sourcePeekText.textContent = "";
  syncSceneGrounding(null);
  updateFlow();
}

function syncSceneGrounding(grounded) {
  document.documentElement.dataset.answerGrounded = String(grounded);
  window.PitchroomScene?.setGrounded?.(grounded);
  window.dispatchEvent(new CustomEvent("pitchroom:answer-grounding", { detail: { grounded } }));
}

function setHeard(question) {
  elements.heard.textContent = question;
  elements.heard.classList.remove("placeholder");
}

function renderAnswer(answerData) {
  state.lastAnswer = answerData.answer || "";
  state.lastSpokenAnswer = answerData.spoken_answer || state.lastAnswer;
  elements.answer.textContent = state.lastAnswer || "I could not find that in the approved sources.";
  elements.answer.classList.remove("placeholder");
  const grounded = Boolean(answerData.grounded);
  syncSceneGrounding(grounded);
  elements.groundingBadge.textContent = grounded ? "Grounded in source" : "No matching source";
  elements.groundingBadge.className = `grounding-badge ${grounded ? "is-grounded" : "is-ungrounded"}`;
  const sources = Array.isArray(answerData.sources) ? answerData.sources : [];
  const sourceRefs = Array.isArray(answerData.source_refs) ? answerData.source_refs : [];
  if (elements.sourcePeek) elements.sourcePeek.hidden = !sources.length;
  if (elements.sourcePeekCitation) elements.sourcePeekCitation.textContent = sources.length ? (sourceRefs[0]?.citation || "Source section") : "";
  if (elements.sourcePeekText) elements.sourcePeekText.textContent = sources.length ? (sourceRefs[0]?.text || sources[0]) : "";
  if (sources.length) {
    elements.evidenceStatus.textContent = `${sources.length} source section${sources.length === 1 ? "" : "s"} used for this response.`;
    elements.evidenceList.innerHTML = "";
    sources.forEach((source, index) => {
      const quote = document.createElement("blockquote");
      quote.className = "evidence-quote";
      const citation = sourceRefs[index]?.citation;
      if (citation) {
        const citationLabel = document.createElement("span");
        citationLabel.className = "evidence-citation";
        citationLabel.textContent = citation;
        quote.append(citationLabel);
      }
      quote.append(document.createTextNode(source));
      elements.evidenceList.append(quote);
    });
  } else {
    elements.evidenceStatus.textContent = "No matching approved-source evidence was found, so Pitchroom declined to invent an answer.";
    elements.evidenceList.innerHTML = '<p class="empty-evidence">No source section matched this question. That refusal is intentional: the answer stays inside the approved brief.</p>';
  }
  elements.playAnswer.hidden = !state.lastAnswer;
  updateFlow();
}

function sourceDisplayName(source) {
  const parts = String(source || "Approved source").split(/[\\/]/).filter(Boolean);
  return parts.at(-1) || "Approved source";
}

async function loadPitch() {
  const pitch = await getJson("/api/pitch");
  const source = sourceDisplayName(pitch.source);
  elements.sourceNameTop.textContent = source;
  elements.sourceNameTop.title = source;
  const chunks = Array.isArray(pitch.chunks) ? pitch.chunks.length : 0;
  const characters = (pitch.text || "").length;
  const metadata = pitch.metadata && typeof pitch.metadata === "object" ? pitch.metadata : {};
  const format = String(metadata.format || "text").toUpperCase();
  const units = metadata.slides ? `${metadata.slides} slides` : metadata.pages ? `${metadata.pages} pages` : `${chunks} source sections`;
  elements.sourceMeta.textContent = `${source} · ${format} · ${units} · ${characters.toLocaleString()} characters`;
  const warnings = Array.isArray(metadata.warnings) ? metadata.warnings.filter(Boolean) : [];
  if (elements.sourceIngestStatus) {
    elements.sourceIngestStatus.dataset.state = warnings.length ? "warning" : "ready";
    elements.sourceIngestStatus.title = warnings.join("\n");
    elements.sourceIngestStatus.textContent = warnings.length
      ? `Review before presenting: ${warnings[0]}`
      : `${format} source ready. Source citations will stay attached to grounded answers.`;
  }
  const sections = Array.isArray(pitch.sections) ? pitch.sections : [];
  elements.sourceExcerpt.textContent = sections.length
    ? sections.map((section) => `${section.citation || "Source section"}\n${section.text || ""}`).join("\n\n")
    : (pitch.text || "No approved source is loaded.");
  if (elements.heroSourceStatus) elements.heroSourceStatus.textContent = "Source connected";
  if (elements.heroConsoleReady) elements.heroConsoleReady.dataset.state = "ready";
  return pitch;
}

async function resetDemo() {
  if (state.sourceSwitching) return;
  setSourceSwitching(true);
  clearError();
  state.typedAbort?.abort();
  if (state.active || state.phase === "arming") stopLiveSession();
  try {
    await getJson("/api/pitch/demo", { method: "POST" });
    state.selectedSample = null;
    await loadPitch();
    renderSampleList();
    setAnswerPlaceholder();
    elements.heard.textContent = "Your question will appear here.";
    elements.heard.classList.add("placeholder");
    elements.liveAnnouncement.textContent = "The included demo source has been restored.";
  } catch (error) {
    if (elements.heroConsoleReady?.dataset.state !== "ready") {
      if (elements.heroSourceStatus) elements.heroSourceStatus.textContent = "Source unavailable";
      if (elements.heroConsoleReady) elements.heroConsoleReady.dataset.state = "error";
    }
    showError(`Could not restore the demo source: ${error.message}`);
  } finally {
    setSourceSwitching(false);
  }
}

function renderSampleList() {
  if (!elements.sampleList) return;
  elements.sampleList.replaceChildren();
  state.samples.forEach((sample) => {
    const card = document.createElement("article");
    card.className = `sample-card${state.selectedSample === sample.id ? " is-selected" : ""}`;
    const heading = document.createElement("h3");
    heading.textContent = sample.title;
    const tagline = document.createElement("p");
    tagline.textContent = sample.tagline;
    const actions = document.createElement("div");
    actions.className = "sample-actions";
    const load = document.createElement("button");
    load.className = "sample-load button button-secondary";
    load.type = "button";
    load.dataset.sampleLoad = sample.id;
    load.textContent = state.selectedSample === sample.id ? "Loaded" : "Use sample";
    const download = document.createElement("a");
    download.className = "sample-download";
    download.href = sample.download_url;
    download.download = sample.filename;
    download.textContent = "Download source";
    actions.append(load, download);
    card.append(heading, tagline, actions);
    sample.questions.forEach((question) => {
      const ask = document.createElement("button");
      ask.className = "sample-question";
      ask.type = "button";
      ask.dataset.sampleQuestion = question;
      ask.textContent = question;
      card.append(ask);
    });
    elements.sampleList.append(card);
  });
}

async function loadSample(sampleId) {
  if (state.sourceSwitching) return;
  setSourceSwitching(true);
  clearError();
  state.typedAbort?.abort();
  if (state.active || state.phase === "arming") stopLiveSession();
  try {
    await getJson(`/api/pitch/sample/${encodeURIComponent(sampleId)}`, { method: "POST" });
    state.selectedSample = sampleId;
    await loadPitch();
    renderSampleList();
    setAnswerPlaceholder();
    elements.heard.textContent = "Your question will appear here.";
    elements.heard.classList.add("placeholder");
    const sampleName = state.samples.find((sample) => sample.id === sampleId)?.title || "Sample source";
    elements.liveAnnouncement.textContent = `${sampleName} is now the approved source.`;
  } catch (error) {
    showError(`Could not load this sample source: ${error.message}`);
  } finally {
    setSourceSwitching(false);
  }
}

async function loadSamples() {
  try {
    const response = await getJson("/api/pitch/samples");
    state.samples = Array.isArray(response) ? response : [];
    renderSampleList();
  } catch (_) {
    elements.sampleList.textContent = "Sample sources are unavailable. You can still add your own material in Assistant Studio.";
  }
}

function clearAudio() {
  // Invalidate callbacks before touching the element. Removing an audio source
  // may still dispatch a late error event in some browsers.
  state.playbackId += 1;
  state.browserSpeechId += 1;
  const cancelBrowserSpeech = state.browserSpeechCancel;
  state.browserSpeechCancel = null;
  if (cancelBrowserSpeech) cancelBrowserSpeech();
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  state.currentSpeech = null;
  const audio = state.currentAudio;
  const audioUrl = state.currentAudioUrl;
  state.currentAudio = null;
  state.currentAudioUrl = null;
  state.speakingStartedAt = 0;
  // A recorder can be collecting an interruption while the server finishes
  // the WAV. Preserve its candidate state as the audio element is attached.
  if (!state.bargeInArmed) state.bargeCandidateAt = 0;
  if (audio) {
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
  }
  if (audioUrl) {
    URL.revokeObjectURL(audioUrl);
  }
}

function selectRecordingOptions() {
  const types = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  const supported = types.find((type) => window.MediaRecorder && MediaRecorder.isTypeSupported(type));
  return supported ? { mimeType: supported } : {};
}

function startRecorder(mode = "live") {
  if (!state.active || !state.stream || !window.MediaRecorder) return false;
  if (state.recorder && state.recorder.state !== "inactive") return false;
  if (mode !== "barge") {
    state.hasSpoken = false;
    state.turnStartedAt = 0;
    state.speechCandidateAt = 0;
    state.silenceStartedAt = 0;
  }
  state.recorderStartedAt = performance.now();
  const recorder = new MediaRecorder(state.stream, selectRecordingOptions());
  const capture = {
    id: ++state.captureId,
    mode,
    accepted: mode !== "barge",
    chunks: [],
    preArmTimer: 0,
    recorder,
    sessionId: state.sessionId,
    turnEpoch: 0,
  };
  state.recorder = recorder;
  state.recorderContext = capture;
  recorder.addEventListener("dataavailable", (event) => {
    if (event.data && event.data.size) capture.chunks.push(event.data);
  });
  recorder.addEventListener("stop", () => {
    if (capture.preArmTimer) {
      window.clearTimeout(capture.preArmTimer);
      capture.preArmTimer = 0;
    }
    const blob = new Blob(capture.chunks, { type: recorder.mimeType || "audio/webm" });
    if (state.recorder === recorder) state.recorder = null;
    if (state.recorderContext === capture) state.recorderContext = null;
    if (
      capture.accepted
      && state.active
      && capture.sessionId === state.sessionId
      && state.phase === "transcribing"
      && state.hasSpoken
      && blob.size > 400
    ) {
      const turnEpoch = capture.turnEpoch || ++state.turnEpoch;
      capture.turnEpoch = turnEpoch;
      processVoiceTurn(blob, capture.sessionId, turnEpoch);
    } else if (
      capture.mode === "barge"
      && !capture.accepted
      && state.active
      && state.bargeInArmed
      && !state.bargeCandidateAt
    ) {
      // Keep the pre-answer capture bounded without dropping WebM headers.
      // A new recorder starts a fresh valid short pre-roll if speech still has
      // not begun after this one is discarded.
      window.setTimeout(() => {
        if (state.active && state.bargeInArmed && !state.bargeCandidateAt && !state.recorder) {
          armBargeCapture();
        }
      }, 40);
    }
  });
  recorder.start(120);
  if (mode === "barge") {
    capture.preArmTimer = window.setTimeout(() => {
      if (
        !capture.accepted
        && state.recorderContext === capture
        && recorder.state !== "inactive"
      ) {
        // Do not let an incomplete candidate keep a buffered WebM recorder
        // alive indefinitely in a throttled tab. The stop handler starts a
        // fresh, valid short pre-roll when the room is still armed.
        state.bargeCandidateAt = 0;
        recorder.stop();
      }
    }, BARGE_PREARM_MAX_MS);
  }
  return true;
}

function finishDetectedTurn(reason) {
  if (!state.recorder || state.recorder.state === "inactive" || !state.recorderContext?.accepted || !state.hasSpoken) return;
  setPhase("transcribing", reason === "limit" ? "Maximum live-turn length reached. Transcribing now." : "Pause detected. Transcribing your question now.");
  state.recorder.stop();
}

function discardBargeCapture() {
  state.bargeCandidateAt = 0;
  const capture = state.recorderContext;
  if (!capture || capture.mode !== "barge" || capture.accepted) return;
  capture.accepted = false;
  if (capture.recorder.state !== "inactive") capture.recorder.stop();
}

function armBargeCapture() {
  if (!state.active || !state.stream) return false;
  const capture = state.recorderContext;
  const hasPreArmedCapture = capture?.mode === "barge" && capture.recorder.state !== "inactive";
  if (hasPreArmedCapture) {
    state.bargeInArmed = true;
    return true;
  }
  state.bargeInArmed = true;
  state.bargeCandidateAt = 0;
  if (startRecorder("barge")) return true;
  state.bargeInArmed = false;
  return false;
}

function disarmBargeCapture() {
  state.bargeInArmed = false;
  discardBargeCapture();
}

async function pauseCaptureForPlayback() {
  state.bargeInArmed = false;
  state.bargeCandidateAt = 0;
  const capture = state.recorderContext;
  if (!capture || capture.recorder.state === "inactive") return;
  capture.accepted = false;
  state.hasSpoken = false;
  await new Promise((resolve) => {
    capture.recorder.addEventListener("stop", resolve, { once: true });
    capture.recorder.stop();
  });
}

function confirmBargeIn() {
  const capture = state.recorderContext;
  const startedAt = state.bargeCandidateAt;
  if (!capture || capture.mode !== "barge" || !startedAt) return;
  // Abort the still-buffering speech request before accepting the new turn.
  // By normal audible playback the WAV has already arrived, so clearAudio()
  // remains the immediate interruption path for the speaker.
  if (state.pendingAbort) state.pendingAbort.abort();
  state.bargeInArmed = false;
  capture.accepted = true;
  capture.turnEpoch = ++state.turnEpoch;
  clearAudio();
  state.hasSpoken = true;
  state.turnStartedAt = startedAt;
  state.silenceStartedAt = 0;
  setPhase("listening", "Reply interrupted. Pitchroom is listening to your new question.");
  elements.stageTitle.textContent = "I heard you — keep speaking.";
  elements.stageCopy.textContent = "The reply has stopped. Pause when your new question is complete and Pitchroom will send it automatically.";
}

function detectBargeIn(rms, now) {
  if (!state.bargeInArmed) return;
  // There is no speaker echo while Kokoro is still preparing the WAV, so allow
  // a new question then. Once playback begins, retain the anti-echo grace.
  const isPlaying = Boolean(state.currentAudio || state.currentSpeech);
  const candidatePredatesPlayback = Boolean(
    state.bargeCandidateAt && state.bargeCandidateAt < state.speakingStartedAt,
  );
  if (isPlaying && !candidatePredatesPlayback && now - state.speakingStartedAt < BARGE_IN_GRACE_MS) return;
  const threshold = Math.max(BARGE_IN_MIN_THRESHOLD, state.voiceThreshold * BARGE_IN_THRESHOLD_MULTIPLIER);
  if (rms <= threshold) {
    if (state.bargeCandidateAt) discardBargeCapture();
    return;
  }
  if (!state.bargeCandidateAt) {
    const capture = state.recorderContext;
    const hasPreArmedCapture = capture?.mode === "barge" && capture.recorder.state !== "inactive";
    if (hasPreArmedCapture || startRecorder("barge")) state.bargeCandidateAt = now;
    return;
  }
  if (now - state.bargeCandidateAt >= BARGE_IN_CONFIRMATION_MS) confirmBargeIn();
}

function updateMeter(level) {
  const scale = Math.max(0.32, Math.min(1.75, 0.3 + level * 24));
  elements.meterBars.forEach((bar, index) => {
    const variance = [0.64, 1.05, 1.38, 0.88, 1.52, 1.08, 0.74, 1.22, 0.62][index];
    bar.style.setProperty("--meter-scale", String(Math.max(0.28, Math.min(1.8, scale * variance))));
  });
  window.PitchroomScene?.setAudioLevel?.(level);
}

function analyseMicrophone() {
  if (!state.active || !state.analyser || !state.analyserData) return;
  state.analyser.getByteTimeDomainData(state.analyserData);
  let sum = 0;
  for (const sample of state.analyserData) {
    const normalized = (sample - 128) / 128;
    sum += normalized * normalized;
  }
  const rms = Math.sqrt(sum / state.analyserData.length);
  updateMeter(rms);
  const now = performance.now();

  if (state.phase === "speaking" || state.bargeInArmed) {
    detectBargeIn(rms, now);
  } else if (state.phase === "listening") {
    if (now < state.calibrationUntil) {
      state.noiseFloor = state.noiseFloor * 0.93 + rms * 0.07;
    } else if (rms < state.voiceThreshold * 0.55) {
      state.noiseFloor = state.noiseFloor * 0.985 + rms * 0.015;
    }
    state.voiceThreshold = Math.max(MIN_VOICE_THRESHOLD, Math.min(MAX_VOICE_THRESHOLD, state.noiseFloor * 3.1 + 0.006));
    const voiced = rms > state.voiceThreshold;

    if (!state.hasSpoken) {
      if (voiced) {
        if (!state.speechCandidateAt) state.speechCandidateAt = now;
        if (now - state.speechCandidateAt >= SPEECH_CONFIRMATION_MS) {
          state.hasSpoken = true;
          state.turnStartedAt = now;
          state.silenceStartedAt = 0;
          updateFlow();
          elements.stageTitle.textContent = "Listening to your question…";
          elements.stageCopy.textContent = "Keep speaking naturally. A brief pause will send this turn automatically.";
          elements.liveAnnouncement.textContent = "Speech detected. Pitchroom is listening to your question.";
        }
      } else {
        state.speechCandidateAt = 0;
        if (now - state.recorderStartedAt > MAX_TURN_MS) {
          const recorder = state.recorder;
          if (recorder && recorder.state !== "inactive") recorder.stop();
          window.setTimeout(() => { if (state.active && state.phase === "listening") startRecorder(); }, 40);
        }
      }
    } else if (voiced) {
      state.silenceStartedAt = 0;
    } else {
      if (!state.silenceStartedAt) state.silenceStartedAt = now;
      if (now - state.silenceStartedAt >= END_OF_TURN_MS) finishDetectedTurn("silence");
    }
    if (state.hasSpoken && state.turnStartedAt && now - state.turnStartedAt >= MAX_TURN_MS) finishDetectedTurn("limit");
  }
  state.meterFrame = requestAnimationFrame(analyseMicrophone);
}

function armNextTurn(announcement = "Pitchroom is listening again.", retainNotice = false) {
  if (!state.active || !state.stream) return;
  if (!retainNotice) clearError();
  disarmBargeCapture();
  state.hasSpoken = false;
  state.calibrationUntil = performance.now() + Math.min(420, CALIBRATION_MS);
  setPhase("listening", announcement);
  if (!startRecorder()) {
    window.setTimeout(() => {
      if (state.active && state.phase === "listening" && !state.recorder) startRecorder();
    }, 80);
  }
}

async function startLiveSession() {
  if (state.sourceSwitching) return;
  if (state.active) {
    stopLiveSession();
    return;
  }
  if (state.phase === "arming") return;
  clearError();
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder || !(window.AudioContext || window.webkitAudioContext)) {
    showError("This browser does not support live microphone capture. Use the typed source question instead.");
    return;
  }
  state.typedAbort?.abort();
  setPhase("arming", "Requesting microphone permission.");
  let sessionId = state.sessionId;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    if (sessionId !== state.sessionId) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    state.active = true;
    sessionId = ++state.sessionId;
    state.stream = stream;
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    state.audioContext = new AudioContextClass();
    await state.audioContext.resume();
    if (!state.active || sessionId !== state.sessionId) return;
    const source = state.audioContext.createMediaStreamSource(stream);
    const analyser = state.audioContext.createAnalyser();
    analyser.fftSize = 2048;
    analyser.smoothingTimeConstant = 0.78;
    source.connect(analyser);
    state.analyser = analyser;
    state.analyserData = new Uint8Array(analyser.fftSize);
    state.noiseFloor = 0.003;
    state.voiceThreshold = MIN_VOICE_THRESHOLD;
    state.calibrationUntil = performance.now() + CALIBRATION_MS;
    armNextTurn("Microphone connected. Pitchroom is listening.");
    state.meterFrame = requestAnimationFrame(analyseMicrophone);
  } catch (error) {
    if (sessionId !== state.sessionId) return;
    if (state.active) stopLiveSession();
    const denied = error && (error.name === "NotAllowedError" || error.name === "SecurityError");
    showError(denied ? "Microphone access was not allowed. Allow it in browser settings, then start the session again." : `Could not start the microphone: ${error.message || "Unknown error."}`);
  }
}

function stopLiveSession() {
  state.sessionId += 1;
  state.turnEpoch += 1;
  state.active = false;
  state.bargeInArmed = false;
  if (state.pendingAbort) {
    state.pendingAbort.abort();
    state.pendingAbort = null;
  }
  if (state.meterFrame) cancelAnimationFrame(state.meterFrame);
  state.meterFrame = null;
  if (state.recorder && state.recorder.state !== "inactive") {
    if (state.recorderContext) state.recorderContext.accepted = false;
    state.recorder.stop();
  }
  state.recorder = null;
  state.recorderContext = null;
  clearAudio();
  if (state.stream) state.stream.getTracks().forEach((track) => track.stop());
  state.stream = null;
  if (state.audioContext) state.audioContext.close().catch(() => {});
  state.audioContext = null;
  state.analyser = null;
  state.analyserData = null;
  updateMeter(0);
  setPhase("ready", "The live session has ended.");
}

async function requestAnswer(question, signal) {
  return getJson("/api/voice/answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
    signal,
  });
}

async function requestSpeech(text, signal) {
  const response = await apiFetch("/api/voice/speak", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal,
  });
  if (!response.ok) {
    let body = null;
    try { body = await response.json(); } catch (_) { /* preserve fallback below */ }
    const error = new Error(responseDetail(body, `Speech request failed (${response.status}).`));
    error.status = response.status;
    throw error;
  }
  return response.blob();
}

function setVoiceReadiness(message, status = "checking") {
  elements.voiceReadiness.textContent = message;
  elements.voiceReadiness.dataset.state = status;
}

function warmSpeechProvider() {
  // This endpoint warms only an explicitly selected local Kokoro model. It is
  // deliberately a no-op for browser and hosted voice settings, so opening the
  // live room never spends provider credits or sends an answer to a provider.
  if (state.speechWarmPromise) return state.speechWarmPromise;
  setVoiceReadiness("Checking the selected voice…");
  state.speechWarmPromise = apiFetch("/api/voice/warm", { method: "POST" })
    .then(async (response) => {
      let readiness = {};
      try { readiness = await response.json(); } catch (_) { /* retain fallback below */ }
      state.speechProvider = readiness.provider || response.headers.get("X-Speech-Provider") || null;
      if (!response.ok) {
        setVoiceReadiness(state.speechProvider === "kokoro"
          ? "Kokoro voice unavailable"
          : "Studio voice unavailable — browser voice will take over.", "fallback");
        return false;
      }
      if (readiness.provider === "kokoro" && readiness.ready) {
        setVoiceReadiness("Kokoro voice ready · local English", "ready");
        return true;
      }
      if (readiness.provider === "browser") {
        setVoiceReadiness("Free browser voice ready", "ready");
        return true;
      }
      setVoiceReadiness("Server voice selected · it will be checked on the first answer.");
      return Boolean(readiness.ready);
    })
    .catch(() => {
      setVoiceReadiness("Voice check unavailable — browser voice will take over.", "fallback");
      return false;
    });
  return state.speechWarmPromise;
}

function selectBrowserVoice() {
  if (!window.speechSynthesis?.getVoices) return null;
  const voices = window.speechSynthesis.getVoices();
  return voices.find((voice) => /en-IN/i.test(voice.lang))
    || voices.find((voice) => /en-US|en-GB/i.test(voice.lang))
    || voices[0]
    || null;
}

function playBrowserSpeech(text, resumeWhenFinished) {
  if (!window.speechSynthesis || !window.SpeechSynthesisUtterance) {
    throw new Error("This browser does not provide a local speech voice.");
  }
  clearAudio();
  const browserSpeechId = state.browserSpeechId;
  const utterance = new window.SpeechSynthesisUtterance(text);
  const voice = selectBrowserVoice();
  utterance.lang = voice?.lang || "en-IN";
  utterance.rate = 0.98;
  utterance.pitch = 1;
  if (voice) utterance.voice = voice;
  state.currentSpeech = utterance;
  state.speakingStartedAt = performance.now();
  setPhase("speaking", "Pitchroom is answering with the free browser voice. Speak over it to interrupt.");
  elements.stageCopy.textContent = "Using the free browser voice locally. Speak over the reply to interrupt it.";

  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (error = null) => {
      if (settled) return;
      settled = true;
      const isCurrent = browserSpeechId === state.browserSpeechId && state.currentSpeech === utterance;
      if (state.browserSpeechCancel === cancel) state.browserSpeechCancel = null;
      if (state.currentSpeech === utterance) state.currentSpeech = null;
      if (!isCurrent) {
        resolve();
        return;
      }
      if (error) {
        reject(error);
        return;
      }
      if (resumeWhenFinished || state.active) armNextTurn("Answer complete. Pitchroom is listening again.");
      else setPhase("ready", "Answer playback complete.");
      resolve();
    };
    const cancel = () => finish();
    state.browserSpeechCancel = cancel;
    utterance.onend = () => finish();
    utterance.onerror = (event) => {
      const reason = event?.error ? ` (${event.error})` : "";
      finish(new Error(`The local browser voice could not speak${reason}.`));
    };
    try {
      window.speechSynthesis.speak(utterance);
      if (state.active && resumeWhenFinished) armBargeCapture();
    } catch (error) {
      finish(error instanceof Error ? error : new Error("The local browser voice could not start."));
    }
  });
}

async function playAnswer(text, resumeWhenFinished, signal) {
  await warmSpeechProvider();
  if (signal?.aborted) throw new DOMException("The speech request was aborted.", "AbortError");
  if (state.speechProvider === "browser") return playBrowserSpeech(text, resumeWhenFinished);
  try {
    const speechBlob = await requestSpeech(text, signal);
    if (signal?.aborted) throw new DOMException("The speech request was aborted.", "AbortError");
    await playBlob(speechBlob, resumeWhenFinished);
  } catch (error) {
    if (error?.name === "AbortError" || signal?.aborted) throw error;
    const serverMessage = error?.message || "The server speech provider is unavailable.";
    if (state.speechProvider === "kokoro") {
      elements.liveAnnouncement.textContent = "Kokoro voice is unavailable. The grounded answer is still shown on screen.";
      setVoiceReadiness("Kokoro voice unavailable", "fallback");
      throw new Error(`Kokoro playback failed: ${serverMessage}`);
    }
    elements.liveAnnouncement.textContent = "Server voice unavailable. Switching to the free browser voice.";
    setVoiceReadiness("Browser voice fallback active", "fallback");
    try {
      await playBrowserSpeech(text, resumeWhenFinished);
    } catch (browserError) {
      throw new Error(`${serverMessage} Browser voice fallback failed: ${browserError?.message || "unknown error."}`);
    }
  }
}

async function playBlob(blob, resumeWhenFinished) {
  clearAudio();
  const audioUrl = URL.createObjectURL(blob);
  const audio = new Audio(audioUrl);
  const playbackId = state.playbackId;
  state.currentAudio = audio;
  state.currentAudioUrl = audioUrl;
  audio.addEventListener("ended", () => {
    if (playbackId !== state.playbackId || state.currentAudio !== audio) return;
    disarmBargeCapture();
    clearAudio();
    if (resumeWhenFinished || state.active) armNextTurn("Answer complete. Pitchroom is listening again.");
    else setPhase("ready", "Answer playback complete.");
  }, { once: true });
  audio.addEventListener("error", () => {
    if (playbackId !== state.playbackId || state.currentAudio !== audio) return;
    disarmBargeCapture();
    clearAudio();
    if (resumeWhenFinished || state.active) armNextTurn("Audio playback was interrupted. Pitchroom is listening again.");
  }, { once: true });
  state.speakingStartedAt = performance.now();
  setPhase("speaking", "Pitchroom is answering aloud.");
  try {
    await audio.play();
    if (playbackId !== state.playbackId || state.currentAudio !== audio) return;
    if (state.active && resumeWhenFinished) armBargeCapture();
  } catch (error) {
    if (playbackId !== state.playbackId) return;
    elements.playAnswer.hidden = false;
    disarmBargeCapture();
    if (resumeWhenFinished) armNextTurn("The answer is ready. This browser needs one tap to play it; Pitchroom is listening again.");
    else setPhase(state.active ? "listening" : "ready", "Answer audio is ready to play.");
  }
}

async function processVoiceTurn(blob, sessionId, turnEpoch) {
  const controller = new AbortController();
  state.pendingAbort = controller;
  try {
    const fileType = blob.type || "audio/webm";
    const extension = fileType.includes("mp4") ? "mp4" : "webm";
    const audio = new File([blob], `pitchroom-question.${extension}`, { type: fileType });
    const formData = new FormData();
    formData.append("file", audio, audio.name);
    const transcription = await getJson("/api/voice/transcribe", { method: "POST", body: formData, signal: controller.signal });
    if (!state.active || sessionId !== state.sessionId || turnEpoch !== state.turnEpoch) return;
    const question = String(transcription.text || "").trim();
    if (!question) throw new Error("No speech was detected. Try asking your question again.");
    setHeard(question);
    setPhase("thinking", "Question transcribed. Finding source evidence now.");
    const answerData = await requestAnswer(question, controller.signal);
    if (!state.active || sessionId !== state.sessionId || turnEpoch !== state.turnEpoch) return;
    renderAnswer(answerData);
    try {
      if (!state.active || sessionId !== state.sessionId || turnEpoch !== state.turnEpoch) return;
      // Start retaining a possible interruption before the server finishes
      // buffering the WAV. This closes the otherwise lost sub-second gap.
      armBargeCapture();
      await playAnswer(answerData.spoken_answer || answerData.answer, true, controller.signal);
    } catch (speechError) {
      if (!state.active || sessionId !== state.sessionId || turnEpoch !== state.turnEpoch) return;
      showError(`The grounded answer is ready, but voice playback is unavailable: ${speechError.message}`, true);
      armNextTurn("The answer is on screen. Voice playback is unavailable, and Pitchroom is listening again.", true);
    }
  } catch (error) {
    if (error.name === "AbortError" || sessionId !== state.sessionId || turnEpoch !== state.turnEpoch) return;
    showError(`Live voice turn could not finish: ${error.message}`, true);
    if (state.active) armNextTurn("That turn could not be completed. Pitchroom is listening again.", true);
  } finally {
    if (state.pendingAbort === controller) state.pendingAbort = null;
  }
}

async function askTypedQuestion(event) {
  event.preventDefault();
  if (elements.textQuestion.disabled || state.sourceSwitching) return;
  const question = elements.textQuestion.value.trim();
  if (question.length < 2) {
    elements.textQuestion.focus();
    return;
  }
  clearError();
  const wasActive = state.active;
  if (wasActive) {
    // A deliberate typed question takes ownership from any live turn that is
    // still transcribing or buffering speech, so stale audio cannot return.
    state.turnEpoch += 1;
    if (state.pendingAbort) state.pendingAbort.abort();
    disarmBargeCapture();
    clearAudio();
  }
  if (state.recorder && state.recorder.state !== "inactive") {
    // Do not let a partly spoken live turn race the intentional typed question.
    state.hasSpoken = false;
    if (state.recorderContext) state.recorderContext.accepted = false;
    state.recorder.stop();
  }
  setHeard(question);
  setPhase("thinking", "Finding source evidence for the typed question.");
  elements.textQuestion.disabled = true;
  elements.askButton.disabled = true;
  const controller = new AbortController();
  state.typedAbort = controller;
  try {
    const answerData = await requestAnswer(question, controller.signal);
    if (controller.signal.aborted) return;
    renderAnswer(answerData);
    elements.textQuestion.value = "";
    if (wasActive) armNextTurn("Typed answer ready. Pitchroom is listening again.");
    else setPhase("ready", "Grounded answer ready.");
  } catch (error) {
    if (error.name === "AbortError" || controller.signal.aborted) return;
    showError(`Could not answer this question: ${error.message}`, wasActive);
    if (wasActive) armNextTurn("Pitchroom is listening again.");
  } finally {
    if (state.typedAbort === controller) state.typedAbort = null;
    elements.textQuestion.disabled = false;
    elements.askButton.disabled = Boolean(state.sourceSwitching);
  }
}

async function manuallyPlayAnswer() {
  if (!state.lastAnswer) return;
  clearError();
  elements.playAnswer.disabled = true;
  let manualController = null;
  let manualTurnEpoch = null;
  try {
    const readyAudio = state.currentAudio?.src ? state.currentAudio : null;
    if (readyAudio) {
      if (state.active) await pauseCaptureForPlayback();
      state.speakingStartedAt = performance.now();
      setPhase("speaking", "Pitchroom is answering aloud.");
      await readyAudio.play();
      if (state.active) armBargeCapture();
      return;
    }
    if (state.active) {
      // Manual playback is an explicit ownership handoff from any automatic
      // live reply that may still be buffering in the background.
      state.turnEpoch += 1;
      if (state.pendingAbort) state.pendingAbort.abort();
      disarmBargeCapture();
      clearAudio();
      await pauseCaptureForPlayback();
    }
    manualTurnEpoch = state.turnEpoch;
    if (state.active) {
      manualController = new AbortController();
      state.pendingAbort = manualController;
    }
    if (state.active) armBargeCapture();
    await playAnswer(state.lastSpokenAnswer || state.lastAnswer, state.active, manualController?.signal);
    if (manualController?.signal.aborted || manualTurnEpoch !== state.turnEpoch) return;
  } catch (error) {
    if (error?.name === "AbortError" || (manualTurnEpoch !== null && manualTurnEpoch !== state.turnEpoch)) return;
    disarmBargeCapture();
    showError(`Could not play the answer: ${error.message}`, true);
    if (state.active) armNextTurn("Voice playback could not start. Pitchroom is listening again.", true);
  } finally {
    if (manualController && state.pendingAbort === manualController) state.pendingAbort = null;
    elements.playAnswer.disabled = false;
  }
}

function bindEvents() {
  elements.liveToggles.forEach((toggle) => {
    toggle.addEventListener("click", () => {
      if (!state.active && toggle.hasAttribute("data-scroll-stage")) {
        document.querySelector("#live-stage")?.scrollIntoView({
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
          block: "start",
        });
      }
      startLiveSession();
    });
  });
  elements.demoReset.addEventListener("click", resetDemo);
  elements.demoResetSource.addEventListener("click", resetDemo);
  elements.sampleList.addEventListener("click", (event) => {
    const question = event.target.closest("[data-sample-question]")?.dataset.sampleQuestion;
    if (question) {
      elements.textQuestion.value = question;
      elements.textQuestionForm.requestSubmit();
      return;
    }
    const sampleId = event.target.closest("[data-sample-load]")?.dataset.sampleLoad;
    if (sampleId) void loadSample(sampleId);
  });
  elements.textQuestionForm.addEventListener("submit", askTypedQuestion);
  elements.playAnswer.addEventListener("click", manuallyPlayAnswer);
  elements.questionPrompts.forEach((prompt) => {
    prompt.addEventListener("click", () => {
      const question = String(prompt.dataset.question || "").trim();
      if (!question) return;
      elements.textQuestion.value = question;
      const askNow = prompt.hasAttribute("data-ask-now");
      const target = askNow && window.matchMedia("(max-width: 880px)").matches
        ? document.querySelector(".conversation-card") : document.querySelector("#live-stage");
      target?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        block: "start",
      });
      if (askNow) elements.textQuestionForm.requestSubmit();
      else window.setTimeout(() => elements.textQuestion.focus(), 420);
    });
  });
  window.addEventListener("beforeunload", stopLiveSession);
}

async function initialise() {
  bindEvents();
  // Start warming while the demo source loads. If Kokoro is selected, model
  // setup happens before the presenter asks the first question.
  void warmSpeechProvider();
  try {
    await loadPitch();
    await loadSamples();
  } catch (error) {
    if (elements.heroSourceStatus) elements.heroSourceStatus.textContent = "Source unavailable";
    if (elements.heroConsoleReady) elements.heroConsoleReady.dataset.state = "error";
    showError(`Could not load the approved source: ${error.message}`);
  }
  setAnswerPlaceholder();
  setPhase("ready");
}

initialise();
