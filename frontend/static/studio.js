const $ = (selector) => document.querySelector(selector);
const state = { mode: "login", assistants: [], active: null, shareToken: "", history: [], shareUrl: "", sessionId: "", speechAudio: null, speechUrl: "", speechCancel: null, speechAbort: null };

async function api(path, options = {}) {
  const response = await fetch(path, { credentials: "same-origin", ...options,
    headers: { Accept: "application/json", ...(options.headers || {}) } });
  let body = {};
  try { body = await response.json(); } catch (_) { /* show a plain HTTP error below */ }
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status}).`);
  return body;
}

function message(element, text, good = false) {
  element.textContent = text;
  element.classList.toggle("is-good", good);
}

function stopSpeech() {
  const finish = state.speechCancel;
  const audio = state.speechAudio;
  const url = state.speechUrl;
  state.speechCancel = null;
  state.speechAudio = null;
  state.speechUrl = "";
  state.speechAbort?.abort();
  state.speechAbort = null;
  finish?.(new DOMException("Speech playback was cancelled.", "AbortError"));
  window.speechSynthesis?.cancel();
  if (audio) { audio.pause(); audio.removeAttribute("src"); audio.load(); }
  if (url) URL.revokeObjectURL(url);
}

function setVoiceDisclosure(provider) {
  const voice = provider === "kokoro" ? "Kokoro’s local English voice"
    : provider === "browser" ? "your browser’s voice" : "the selected speech provider";
  document.querySelectorAll(".voice-disclosure").forEach((element) => {
    element.textContent = `Voice questions use your browser’s speech recognition. Spoken replies use ${voice}. Pitchroom does not retain microphone recordings.`;
  });
}

async function warmVoice(path, statusId) {
  try {
    const result = await api(path, { method: "POST" });
    setVoiceDisclosure(result.provider);
  } catch (error) {
    message($(statusId), `Spoken replies are not ready: ${error.message}. The written answers are still available.`);
  }
}

function savedShareUrl(id) {
  try { return localStorage.getItem(`pitchroom_share_${id}`) || ""; } catch (_) { return ""; }
}

function storeShareUrl(id, url) {
  try { localStorage.setItem(`pitchroom_share_${id}`, url); } catch (_) { /* the owner can regenerate the link */ }
}

function clearShareUrl(id) {
  try { localStorage.removeItem(`pitchroom_share_${id}`); } catch (_) { /* no browser storage to clear */ }
}

function conversationSessionId() {
  try {
    const saved = sessionStorage.getItem("pitchroom_conversation_session");
    if (saved) return saved;
    const id = crypto.randomUUID();
    sessionStorage.setItem("pitchroom_conversation_session", id);
    return id;
  } catch (_) { return crypto.randomUUID(); }
}

function showAuth(mode = "login") {
  state.mode = mode;
  $("#auth-view").hidden = false;
  $("#studio-view").hidden = true;
  $("#topbar-account").hidden = true;
  $("#login-tab").setAttribute("aria-selected", String(mode === "login"));
  $("#register-tab").setAttribute("aria-selected", String(mode === "register"));
  $("#auth-title").textContent = mode === "login" ? "Welcome back" : "Create your account";
  $("#auth-copy").textContent = mode === "login" ? "Sign in to open your assistants." : "Set up a private workspace for your approved sources.";
  $("#auth-submit").innerHTML = `${mode === "login" ? "Sign in" : "Create account"} <span aria-hidden="true">→</span>`;
  $("#auth-password").autocomplete = mode === "login" ? "current-password" : "new-password";
  $("#auth-password").minLength = mode === "register" ? 12 : 1;
  $("#invite-field").hidden = mode !== "register";
  $("#auth-message").textContent = "";
}

function showStudio(email) {
  $("#auth-view").hidden = true;
  $("#studio-view").hidden = false;
  $("#shared-workspace").hidden = true;
  $("#owner-workspace").hidden = false;
  $("#topbar-account").hidden = false;
  $("#account-email").textContent = email;
}

function assistantButton(item) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = item.name;
  button.setAttribute("aria-current", String(item.id === state.active?.id));
  button.addEventListener("click", () => openAssistant(item.id));
  return button;
}

async function loadAssistants(selectId) {
  state.assistants = await api("/api/assistants");
  $("#assistant-count").textContent = state.assistants.length;
  const list = $("#assistant-list");
  list.replaceChildren(...state.assistants.map(assistantButton));
  if (selectId) return openAssistant(selectId);
  if (state.active && state.assistants.some((item) => item.id === state.active.id)) return openAssistant(state.active.id);
  if (state.assistants.length) return openAssistant(state.assistants[0].id);
  const created = await api("/api/assistants", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: "My knowledge assistant" }) });
  state.assistants.unshift(created);
  return loadAssistants(created.id);
}

function sourceElement(source) {
  const card = document.createElement("article");
  card.className = "source-item";
  const top = document.createElement("div");
  top.className = "source-item-top";
  const checkbox = document.createElement("input");
  checkbox.className = "source-check";
  checkbox.type = "checkbox";
  checkbox.checked = source.approved;
  checkbox.setAttribute("aria-label", `${source.approved ? "Remove" : "Approve"} ${source.name} ${source.approved ? "from answers" : "for answers"}`);
  checkbox.addEventListener("change", async () => {
    checkbox.disabled = true;
    try {
      await api(`/api/assistants/${state.active.id}/sources/${source.id}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approved: checkbox.checked }),
      });
      await refreshAssistant();
    } catch (error) { checkbox.checked = source.approved; message($("#source-message"), error.message); }
    finally { checkbox.disabled = false; }
  });
  const title = document.createElement("div");
  title.className = "source-title";
  title.append(document.createTextNode(source.name));
  const kind = document.createElement("span");
  kind.className = "source-kind";
  kind.textContent = `${source.kind === "website" ? "Website page" : "Document"} · ${source.approved ? "Approved" : "Needs review"}`;
  title.append(kind);
  const actions = document.createElement("div");
  actions.className = "source-actions";
  const remove = document.createElement("button");
  remove.type = "button";
  remove.textContent = "Remove";
  remove.setAttribute("aria-label", `Remove ${source.name}`);
  remove.addEventListener("click", async () => {
    if (!confirm(`Remove “${source.name}” from this assistant?`)) return;
    try { await api(`/api/assistants/${state.active.id}/sources/${source.id}`, { method: "DELETE" }); await refreshAssistant(); }
    catch (error) { message($("#source-message"), error.message); }
  });
  actions.append(remove);
  top.append(checkbox, title, actions);
  card.append(top);
  const sample = source.sections?.slice(0, 2).map((part) => part.text).join(" ") || "No readable text was extracted.";
  const preview = document.createElement("p");
  preview.className = "source-preview";
  preview.textContent = sample.slice(0, 240);
  card.append(preview);
  const warnings = source.metadata?.warnings || [];
  if (warnings.length) {
    const warning = document.createElement("p");
    warning.className = "source-warning";
    warning.textContent = warnings.join(" ");
    card.append(warning);
  }
  if (source.metadata?.imported_at) {
    const imported = new Date(source.metadata.imported_at);
    const timestamp = document.createElement("p");
    timestamp.className = "source-preview";
    timestamp.textContent = `Imported ${Number.isNaN(imported.getTime()) ? "recently" : imported.toLocaleString()}`;
    card.append(timestamp);
  }
  if (source.url) {
    const origin = document.createElement("p");
    origin.className = "source-preview";
    origin.textContent = source.url;
    card.append(origin);
  }
  return card;
}

async function addStarterSample(sample, button) {
  const assistantId = state.active?.id;
  const existingSources = state.active?.sources || [];
  if (!assistantId) return;
  button.disabled = true;
  message($("#source-message"), `Adding ${sample.title}…`);
  try {
    const response = await fetch(sample.download_url, { credentials: "same-origin" });
    if (!response.ok) throw new Error(`Sample download failed (${response.status}).`);
    const extensionAt = sample.filename.lastIndexOf(".");
    const stem = extensionAt < 0 ? sample.filename : sample.filename.slice(0, extensionAt);
    const extension = extensionAt < 0 ? "" : sample.filename.slice(extensionAt);
    let copy = 1;
    let filename = `Sample - ${stem}${extension}`;
    while (existingSources.some((source) => source.name.toLowerCase() === filename.toLowerCase())) {
      filename = `Sample - ${stem} (${++copy})${extension}`;
    }
    const file = new File([await response.blob()], filename, {
      type: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    });
    const data = new FormData();
    data.append("file", file);
    const result = await api(`/api/assistants/${assistantId}/sources/files`, { method: "POST", body: data });
    if (state.active?.id === assistantId) {
      await refreshAssistant();
      message($("#source-message"), result.status === "unchanged"
        ? `${sample.title} is already in this assistant.`
        : `${sample.title} added. Review and approve it before asking questions.`, true);
    }
  } catch (error) {
    if (state.active?.id === assistantId) message($("#source-message"), error.message);
  } finally { button.disabled = false; }
}

async function loadStarterSamples() {
  const list = $("#starter-sample-list");
  try {
    const samples = await api("/api/pitch/samples");
    list.replaceChildren(...samples.map((sample) => {
      const card = document.createElement("article");
      card.className = "starter-sample-card";
      const title = document.createElement("strong");
      title.textContent = sample.title;
      const description = document.createElement("p");
      description.textContent = sample.tagline;
      const add = document.createElement("button");
      add.type = "button";
      add.className = "secondary-button";
      add.textContent = "Add sample";
      add.setAttribute("aria-label", `Add ${sample.title} sample to this assistant`);
      add.addEventListener("click", () => { void addStarterSample(sample, add); });
      card.append(title, description, add);
      return card;
    }));
    if (!samples.length) list.textContent = "Sample decks are unavailable. You can still upload your own document.";
  } catch (_) { list.textContent = "Sample decks are unavailable. You can still upload your own document."; }
}

function setSharePanel(assistant) {
  const panel = $("#publish-status");
  panel.hidden = !assistant.published;
  if (!assistant.published) {
    clearShareUrl(assistant.id);
    return;
  }
  state.shareUrl = savedShareUrl(assistant.id);
  $("#share-url").value = state.shareUrl || "Share link is on the device that created it. Generate a fresh link to recover it.";
  $("#share-url").disabled = !state.shareUrl;
  $("#copy-share").disabled = !state.shareUrl;
  $("#publish-copy").textContent = assistant.published_stale
    ? "The active link still uses an older approved snapshot. Refresh it after source changes."
    : state.shareUrl ? "Anyone with this link can ask from the approved source snapshot."
      : "This link is active, but its URL is not saved on this device. Generate a new link to replace it.";
}

async function openAssistant(id) {
  const assistant = await api(`/api/assistants/${id}`);
  state.active = assistant;
  state.history = [];
  $("#assistant-list").replaceChildren(...state.assistants.map(assistantButton));
  $("#assistant-name").value = assistant.name;
  const approved = assistant.sources.filter((source) => source.approved).length;
  $("#assistant-summary").textContent = `${approved} approved · ${assistant.sources.length - approved} to review · ${assistant.sources.length} total source${assistant.sources.length === 1 ? "" : "s"}`;
  $("#source-count").textContent = assistant.sources.length;
  $("#source-list").replaceChildren(...(assistant.sources.length ? assistant.sources.map(sourceElement) : [Object.assign(document.createElement("p"), { className: "empty-note", textContent: "Add a website or document to start. New sources stay out of answers until you approve them." })]));
  $("#publish-assistant").textContent = `${assistant.published ? "Refresh" : "Publish"} approved sources ↗`;
  $("#publish-assistant").classList.toggle("is-stale", assistant.published_stale);
  setSharePanel(assistant);
  await refreshMetrics();
  void warmVoice(`/api/assistants/${assistant.id}/voice/warm`, "#question-message");
}

async function refreshAssistant() { await loadAssistants(state.active.id); }

async function refreshMetrics() {
  if (!state.active) return;
  const data = await api(`/api/assistants/${state.active.id}/metrics`);
  $("#metric-questions").textContent = data.questions;
  $("#metric-sessions").textContent = data.sessions;
  $("#metric-unanswered").textContent = data.unanswered;
  $("#metric-helpful").textContent = data.helpful;
  $("#metric-not-helpful").textContent = data.not_helpful;
  $("#metric-latency").textContent = `${Math.round(data.avg_latency_ms)} ms`;
  $("#metric-tokens").textContent = Number(data.embedding_tokens).toLocaleString();
  $("#metric-cost").textContent = `$${Number(data.avg_embedding_cost_per_session_usd).toFixed(6)}`;
}

async function startPrivateStudio(email) {
  showStudio(email);
  await loadAssistants();
}

function renderSources(container, result) {
  const evidence = document.createElement("div");
  evidence.className = "evidence";
  const refs = result.source_refs || [];
  refs.forEach((ref) => {
    const quote = document.createElement("blockquote");
    const citation = document.createElement(ref.url ? "a" : "span");
    citation.className = ref.url ? "evidence-link" : "evidence-label";
    citation.textContent = ref.citation || "Source passage";
    if (ref.url) { citation.href = ref.url; citation.target = "_blank"; citation.rel = "noopener noreferrer"; }
    quote.append(citation, document.createElement("br"), document.createTextNode(ref.text));
    evidence.append(quote);
  });
  if (refs.length) container.append(evidence);
}

function browserSpeak(text) {
  if (!("speechSynthesis" in window) || !window.SpeechSynthesisUtterance) {
    throw new Error("This browser does not provide a local speech voice.");
  }
  return new Promise((resolve, reject) => {
    let finished = false;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.98;
    const finish = (error) => {
      if (finished) return;
      finished = true;
      if (state.speechCancel === cancel) state.speechCancel = null;
      if (error) reject(error); else resolve();
    };
    const cancel = () => finish(new DOMException("Speech playback was cancelled.", "AbortError"));
    state.speechCancel = cancel;
    utterance.onend = () => finish();
    utterance.onerror = () => finish(new Error("The browser voice could not speak this answer."));
    window.speechSynthesis.speak(utterance);
  });
}

async function speak(text, answerId, shared) {
  stopSpeech();
  const controller = new AbortController();
  state.speechAbort = controller;
  const base = shared ? `/api/shared/${encodeURIComponent(state.shareToken)}` : `/api/assistants/${state.active.id}`;
  try {
    const response = await fetch(`${base}/answers/${encodeURIComponent(answerId)}/speech`, {
      method: "POST", credentials: "same-origin", signal: controller.signal,
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
    });
    if (response.status === 409) return await browserSpeak(text);
    if (!response.ok) {
      let body = {};
      try { body = await response.json(); } catch (_) { /* keep the HTTP status fallback */ }
      throw new Error(body.detail || `Speech request failed (${response.status}).`);
    }
    const url = URL.createObjectURL(await response.blob());
    const audio = new Audio(url);
    state.speechAudio = audio;
    state.speechUrl = url;
    await new Promise((resolve, reject) => {
      let finished = false;
      const finish = (error) => {
        if (finished) return;
        finished = true;
        if (state.speechAudio === audio) {
          state.speechAudio = null;
          state.speechUrl = "";
          URL.revokeObjectURL(url);
        }
        if (state.speechCancel === cancel) state.speechCancel = null;
        if (error) reject(error); else resolve();
      };
      const cancel = () => finish(new DOMException("Speech playback was cancelled.", "AbortError"));
      state.speechCancel = cancel;
      audio.addEventListener("ended", () => finish(), { once: true });
      audio.addEventListener("error", () => finish(new Error("The server voice returned audio that this browser could not play.")), { once: true });
      audio.play().catch((error) => finish(new Error(`Audio playback could not start: ${error.message}`)));
    });
  } finally {
    if (state.speechAbort === controller) state.speechAbort = null;
  }
}

function appendAnswer(container, result, onFeedback, shared, status) {
  const answer = document.createElement("div");
  answer.className = "message message-answer";
  answer.append(document.createTextNode(result.answer || "I could not find that in the approved sources."));
  renderSources(answer, result);
  const feedback = document.createElement("div");
  feedback.className = "answer-feedback";
  if (result.grounded) {
    const listen = document.createElement("button");
    listen.type = "button";
    listen.textContent = "Play answer";
    listen.setAttribute("aria-label", "Play spoken answer");
    const play = async () => {
      listen.disabled = true;
      listen.textContent = "Preparing voice…";
      try {
        await speak(result.spoken_answer || result.answer, result.answer_id, shared);
        listen.textContent = "Play again";
      } catch (error) {
        if (error.name === "AbortError") { listen.textContent = "Play answer"; return; }
        listen.textContent = "Try voice again";
        message($(status), `The answer is ready, but voice playback failed: ${error.message}`);
      } finally { listen.disabled = false; }
    };
    listen.addEventListener("click", () => { void play(); });
    feedback.append(listen);
    void play();
  }
  for (const [rating, label] of [[1, "Helpful"], [-1, "Not helpful"]]) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", () => onFeedback(result.answer_id, rating, button));
    feedback.append(button);
  }
  answer.append(feedback);
  container.append(answer);
  container.scrollTop = container.scrollHeight;
}

async function ask(question, options = {}) {
  const shared = options.shared === true;
  const transcript = shared ? $("#shared-conversation") : $("#conversation");
  const status = shared ? $("#shared-message") : $("#question-message");
  const input = shared ? $("#shared-question-input") : $("#question-input");
  const askButton = (shared ? $("#shared-question-form") : $("#question-form")).querySelector('button[type="submit"]');
  const trimmed = question.trim();
  if (!trimmed) return;
  transcript.querySelector(".conversation-empty")?.remove();
  const bubble = document.createElement("div");
  bubble.className = "message message-question";
  bubble.textContent = trimmed;
  transcript.append(bubble);
  input.value = "";
  askButton.disabled = true;
  status.textContent = "Looking through approved sources…";
  try {
    const path = shared ? `/api/shared/${encodeURIComponent(state.shareToken)}/answer` : `/api/assistants/${state.active.id}/answer`;
    const result = await api(path, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: trimmed, history: state.history, session_id: state.sessionId }) });
    state.history.push({ role: "user", content: trimmed }, { role: "assistant", content: result.answer || "" });
    state.history = state.history.slice(-8);
    appendAnswer(transcript, result, async (answerId, rating, button) => {
      try { await api(shared ? `/api/shared/${encodeURIComponent(state.shareToken)}/feedback` : `/api/assistants/${state.active.id}/feedback`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ answer_id: answerId, rating }),
      }); button.textContent = "Thanks"; button.disabled = true; if (!shared) await refreshMetrics(); }
      catch (error) { message(status, error.message); }
    }, shared, shared ? "#shared-message" : "#question-message");
    status.textContent = "";
    if (!shared) await refreshMetrics();
  } catch (error) { message(status, error.message); }
  finally { askButton.disabled = false; input.focus(); }
}

function bindVoice(buttonId, inputId, formId, statusId) {
  const button = $(buttonId);
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) { button.title = "Voice input is unavailable in this browser."; button.addEventListener("click", () => message($(statusId), "Voice input is not available in this browser. You can type your question instead.")); return; }
  button.addEventListener("click", () => {
    const recognition = new Recognition();
    recognition.lang = navigator.language || "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    button.classList.add("is-listening");
    button.disabled = true;
    button.setAttribute("aria-pressed", "true");
    message($(statusId), "Listening… speak your question.");
    stopSpeech();
    recognition.onresult = (event) => {
      $(inputId).value = event.results[0][0].transcript;
      $(formId).requestSubmit();
    };
    recognition.onerror = () => message($(statusId), "Could not hear that. Please try again or type your question.");
    recognition.onend = () => { button.classList.remove("is-listening"); button.setAttribute("aria-pressed", "false"); button.disabled = false; };
    try { recognition.start(); }
    catch (_) { button.disabled = false; button.classList.remove("is-listening"); button.setAttribute("aria-pressed", "false"); message($(statusId), "Could not start voice input. Please try again or type your question."); }
  });
}

async function initializeShared() {
  state.shareToken = decodeURIComponent(location.pathname.split("/").at(-1));
  $("#auth-view").hidden = true;
  $("#studio-view").hidden = false;
  $("#studio-view").classList.add("is-shared");
  $("#owner-workspace").hidden = true;
  $("#shared-workspace").hidden = false;
  $("#topbar-account").hidden = true;
  $(".topbar-purpose").textContent = "A private link to approved knowledge.";
  try {
    const data = await api(`/api/shared/${encodeURIComponent(state.shareToken)}`);
    $("#shared-name").textContent = data.name;
    $("#shared-sources").replaceChildren(...data.sources.map((source) => {
      const pill = document.createElement("span"); pill.className = "shared-source-pill";
      const name = source.url ? document.createElement("a") : document.createElement("span");
      name.textContent = source.name;
      if (source.url) { name.href = source.url; name.target = "_blank"; name.rel = "noopener noreferrer"; }
      pill.append(name); return pill;
    }));
    await warmVoice(`/api/shared/${encodeURIComponent(state.shareToken)}/voice/warm`, "#shared-message");
    if (data.retrieval_provider === "openai") {
      $("#shared-question-form .voice-disclosure").textContent += " Semantic search also sends approved passages and your question to OpenAI for embeddings.";
    }
  } catch (error) { $("#shared-name").textContent = "This assistant link is unavailable."; message($("#shared-message"), error.message); $("#shared-question-form").hidden = true; }
}

async function initialize() {
  state.sessionId = conversationSessionId();
  $("#shared-question-form").addEventListener("submit", (event) => { event.preventDefault(); ask($("#shared-question-input").value, { shared: true }); });
  const token = location.pathname.match(/^\/s\/([^/]+)$/)?.[1];
  if (token) { bindVoice("#shared-voice-question", "#shared-question-input", "#shared-question-form", "#shared-message"); await initializeShared(); return; }
  void loadStarterSamples();
  $("#login-tab").addEventListener("click", () => showAuth("login"));
  $("#register-tab").addEventListener("click", () => showAuth("register"));
  $("#auth-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const action = state.mode === "login" ? "login" : "register";
    $("#auth-submit").disabled = true;
    message($("#auth-message"), "Opening your workspace…");
    try {
      const user = await api(`/api/auth/${action}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        email: $("#auth-email").value, password: $("#auth-password").value, invite_code: $("#auth-invite").value,
      }) });
      await startPrivateStudio(user.email);
    } catch (error) { message($("#auth-message"), error.message); }
    finally { $("#auth-submit").disabled = false; }
  });
  $("#sign-out").addEventListener("click", async () => { await api("/api/auth/logout", { method: "POST" }); state.active = null; showAuth("login"); });
  $("#create-assistant-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = $("#new-assistant-name").value.trim(); if (!name) return;
    try { const created = await api("/api/assistants", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) }); $("#new-assistant-name").value = ""; await loadAssistants(created.id); }
    catch (error) { message($("#source-message"), error.message); }
  });
  $("#assistant-name").addEventListener("change", async () => {
    if (!state.active || !$("#assistant-name").value.trim()) return;
    try { await api(`/api/assistants/${state.active.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: $("#assistant-name").value.trim() }) }); await loadAssistants(state.active.id); }
    catch (error) { message($("#source-message"), error.message); }
  });
  $("#delete-assistant").addEventListener("click", async () => {
    if (!state.active || !confirm(`Delete “${state.active.name}”, its sources, and its published link? This cannot be undone.`)) return;
    try { await api(`/api/assistants/${state.active.id}`, { method: "DELETE" }); state.active = null; await loadAssistants(); }
    catch (error) { message($("#source-message"), error.message); }
  });
  $("#source-file").addEventListener("change", async (event) => {
    const file = event.target.files?.[0]; if (!file || !state.active) return;
    const data = new FormData(); data.append("file", file);
    message($("#source-message"), "Reading document…");
    try { const result = await api(`/api/assistants/${state.active.id}/sources/files`, { method: "POST", body: data }); await refreshAssistant(); message($("#source-message"), `${result.source} added. Review and approve it before asking questions.`, true); }
    catch (error) { message($("#source-message"), error.message); }
    finally { event.target.value = ""; }
  });
  $("#website-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("#website-submit"); button.disabled = true; button.textContent = "Importing…";
    message($("#source-message"), "Checking public pages and robots.txt. Large sites can take up to 45 seconds.");
    try {
      const result = await api(`/api/assistants/${state.active.id}/sources/websites`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: $("#website-url").value.trim() }) });
      await refreshAssistant();
      const summary = `${result.added} new, ${result.updated} changed, ${result.unchanged} unchanged, ${result.skipped} skipped, ${result.failed.length} failed.`;
      const note = result.truncated ? " The 100-page, 25 MB, or 45-second import limit was reached." : "";
      const skipped = result.skipped_pages || [];
      const failed = result.failed || [];
      const details = $("#import-results");
      details.hidden = !skipped.length && !failed.length;
      details.open = Boolean(failed.length);
      const fillList = (selector, values) => $(selector).replaceChildren(...(values.length ? values.map((value) => { const li = document.createElement("li"); li.textContent = value; return li; }) : [Object.assign(document.createElement("li"), { textContent: "None" })]));
      fillList("#skipped-pages", skipped);
      fillList("#failed-pages", failed);
      message($("#source-message"), `${summary}${note} Review each new page before approving it.`, true);
    } catch (error) { message($("#source-message"), error.message); }
    finally { button.disabled = false; button.textContent = "Import site"; }
  });
  $("#question-form").addEventListener("submit", (event) => { event.preventDefault(); ask($("#question-input").value); });
  document.querySelectorAll("[data-prompt]").forEach((button) => button.addEventListener("click", () => { $("#question-input").value = button.dataset.prompt; $("#question-form").requestSubmit(); }));
  bindVoice("#voice-question", "#question-input", "#question-form", "#question-message");
  $("#publish-assistant").addEventListener("click", async () => {
    if (!confirm("Anyone with the link can ask questions from a snapshot of all approved sources. Publish this snapshot?")) return;
    try { const result = await api(`/api/assistants/${state.active.id}/publish`, { method: "POST" }); state.shareUrl = new URL(result.url, location.origin).href; storeShareUrl(state.active.id, state.shareUrl); await loadAssistants(state.active.id); message($("#source-message"), "Approved source snapshot published.", true); }
    catch (error) { message($("#source-message"), error.message); }
  });
  $("#copy-share").addEventListener("click", async () => { try { await navigator.clipboard.writeText($("#share-url").value); $("#copy-share").textContent = "Copied"; setTimeout(() => { $("#copy-share").textContent = "Copy link"; }, 1600); } catch (_) { $("#share-url").select(); document.execCommand("copy"); } });
  $("#unpublish-assistant").addEventListener("click", async () => {
    if (!confirm("Revoke the public link now? People with it will no longer be able to open this assistant.")) return;
    try { await api(`/api/assistants/${state.active.id}/publish`, { method: "DELETE" }); await loadAssistants(state.active.id); message($("#source-message"), "The public link has been revoked.", true); }
    catch (error) { message($("#source-message"), error.message); }
  });
  try { const user = await api("/api/auth/me"); await startPrivateStudio(user.email); }
  catch (_) { showAuth("login"); }
}

document.addEventListener("DOMContentLoaded", () => { initialize().catch((error) => { console.error(error); showAuth("login"); message($("#auth-message"), "The studio could not load. Refresh the page and try again."); }); });
