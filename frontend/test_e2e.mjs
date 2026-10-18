// Run with: node --test frontend/test_e2e.mjs
// Requires the project's Python venv and a local Chrome installation.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const chrome = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

async function freePorts(count) {
  const servers = Array.from({ length: count }, () => createServer());
  await Promise.all(servers.map((server) => new Promise((resolve) => server.listen(0, "127.0.0.1", resolve))));
  const ports = servers.map((server) => server.address().port);
  await Promise.all(servers.map((server) => new Promise((resolve) => server.close(resolve))));
  return ports;
}

async function until(check, timeout = 10000) {
  const deadline = Date.now() + timeout;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const value = await check();
      if (value) return value;
    } catch (error) { lastError = error; /* startup and browser navigation are asynchronous */ }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error(`Timed out waiting for browser state${lastError ? `: ${lastError.message}` : ""}`);
}

async function stop(process) {
  if (process.exitCode !== null || process.signalCode !== null) return;
  await new Promise((resolve) => {
    process.once("close", resolve);
    process.kill();
  });
}

function silentWav() {
  const samples = 8000;
  const wav = Buffer.alloc(44 + samples * 2);
  wav.write("RIFF"); wav.writeUInt32LE(wav.length - 8, 4); wav.write("WAVEfmt ", 8);
  wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(16000, 24); wav.writeUInt32LE(32000, 28);
  wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34);
  wav.write("data", 36); wav.writeUInt32LE(samples * 2, 40);
  return wav.toString("base64");
}

test("typed evidence and a full voice turn in Chrome", { timeout: 90000 }, async () => {
  const [appPort, debugPort] = await freePorts(2);
  const profile = await mkdtemp(join(tmpdir(), "pitchroom-e2e-"));
  const sourcePath = join(profile, "returns.txt");
  await writeFile(sourcePath, "Refunds are accepted for 30 days after purchase. Contact support@example.com for help.\n");
  const server = spawn(join(root, ".venv/bin/python"), ["-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", String(appPort)], {
    cwd: join(root, "backend"),
    env: { ...process.env, TTS_PROVIDER: "browser", ANSWER_GENERATION_PROVIDER: "extractive", PITCHROOM_ACCESS_TOKEN: "", PITCHROOM_DATABASE_PATH: join(profile, "studio.sqlite3") },
    stdio: "ignore",
  });
  const browser = spawn(chrome, ["--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--autoplay-policy=no-user-gesture-required", `--user-data-dir=${profile}`, `--remote-debugging-port=${debugPort}`, "about:blank"], { stdio: "ignore" });
  let ws;
  try {
    await until(async () => (await fetch(`http://127.0.0.1:${appPort}/health`)).ok, 30000);
    const target = await until(async () => (await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json()).find((item) => item.type === "page"));
    ws = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => { ws.addEventListener("open", resolve, { once: true }); ws.addEventListener("error", reject, { once: true }); });

    let id = 0;
    const pending = new Map();
    const errors = [];
    let transcriptions = 0;
    let speeches = 0;
    const call = (method, params = {}) => new Promise((resolve, reject) => {
      const requestId = ++id;
      pending.set(requestId, { resolve, reject });
      ws.send(JSON.stringify({ id: requestId, method, params }));
    });
    const evaluate = async (expression) => {
      const reply = await call("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
      if (reply.exceptionDetails) throw new Error(reply.exceptionDetails.text);
      return reply.result.value;
    };
    ws.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id) {
        const waiter = pending.get(message.id);
        pending.delete(message.id);
        if (message.error) waiter.reject(new Error(message.error.message));
        else waiter.resolve(message.result);
      } else if (message.method === "Runtime.exceptionThrown") {
        errors.push(message.params.exceptionDetails.text);
      } else if (message.method === "Fetch.requestPaused") {
        const { requestId, request } = message.params;
        const isTranscript = request.url.includes("/api/voice/transcribe");
        if (isTranscript) transcriptions += 1;
        else speeches += 1;
        void call("Fetch.fulfillRequest", {
          requestId,
          responseCode: 200,
          responseHeaders: [{ name: "Content-Type", value: isTranscript ? "application/json" : "audio/wav" }],
          body: isTranscript
            ? Buffer.from(JSON.stringify({ text: "What problem does Pitchroom AI solve?" })).toString("base64")
            : silentWav(),
        }).catch((error) => errors.push(error.message));
      }
    });
    await call("Page.enable");
    await call("Runtime.enable");
    await call("Fetch.enable", { patterns: [
      { urlPattern: "*/api/voice/transcribe", requestStage: "Request" },
      { urlPattern: "*/api/voice/speak", requestStage: "Request" },
      { urlPattern: "*/api/assistants/*/answers/*/speech", requestStage: "Request" },
      { urlPattern: "*/api/shared/*/answers/*/speech", requestStage: "Request" },
    ] });
    await call("Page.addScriptToEvaluateOnNewDocument", { source: `
      window.__phases = [];
      window.addEventListener("pitchroom:voice-phase", (event) => window.__phases.push(event.detail.phase));
      navigator.mediaDevices.getUserMedia = async () => {
        const context = new AudioContext();
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        const destination = context.createMediaStreamDestination();
        oscillator.frequency.value = 280;
        gain.gain.value = 0;
        oscillator.connect(gain).connect(destination);
        oscillator.start();
        await context.resume();
        window.__micGain = gain.gain;
        window.__micStream = destination.stream;
        return destination.stream;
      };
      // Keep browser TTS timing deterministic without calling a provider.
      window.__ttsDelay = 500;
      window.speechSynthesis.speak = (utterance) => setTimeout(() => utterance.onend?.(), window.__ttsDelay);
      window.speechSynthesis.cancel = () => {};
      window.SpeechRecognition = class {
        start() { setTimeout(() => { this.onerror?.({ error: "not-allowed" }); this.onend?.(); }, 0); }
      };
    ` });
    await call("Page.navigate", { url: `http://127.0.0.1:${appPort}/` });
    try {
      await until(() => evaluate("document.querySelector('#stage-card')?.classList.contains('is-ready') && document.querySelector('#source-name-top')?.textContent !== 'Loading…'"), 20000);
    } catch (error) {
      const detail = await evaluate("JSON.stringify({ url: location.href, ready: document.readyState, stage: document.querySelector('#stage-card')?.className, source: document.querySelector('#source-name-top')?.textContent, error: document.querySelector('#voice-error')?.textContent })");
      throw new Error(`${error.message}: ${detail}; browserErrors=${errors.join('; ')}`);
    }

    await evaluate("document.querySelector('[data-ask-now]').click()");
    assert.equal(await evaluate("document.querySelector('#agent-trace-status').textContent"), "Finding source evidence");
    await until(() => evaluate("document.querySelector('#grounding-badge').textContent === 'Grounded in source' && document.querySelectorAll('#evidence-list blockquote').length > 0"));
    assert.match(await evaluate("document.querySelector('#answer-copy').textContent"), /pitch|founder|deck/i);
    assert.equal(await evaluate("document.querySelector('#source-peek').hidden"), false);
    assert.ok(await evaluate("document.querySelector('#source-peek-citation').textContent.length > 0"));
    assert.ok(await evaluate("document.querySelector('#source-peek-text').textContent.length > 0"));

    await evaluate("document.querySelector('#text-question').value = 'What is Pitchroom AI’s Series B valuation?'; document.querySelector('#text-question-form').requestSubmit()");
    await until(() => evaluate("document.querySelector('#grounding-badge').textContent === 'No matching source'"));
    assert.match(await evaluate("document.querySelector('#answer-copy').textContent"), /could not find/i);
    assert.equal(await evaluate("document.querySelector('#source-peek').hidden"), true);

    await evaluate("document.querySelector('#live-toggle-stage').click()");
    await until(() => evaluate("document.documentElement.dataset.voicePhase === 'listening'"));
    assert.equal(await evaluate("document.querySelector('#live-toggle-stage').getAttribute('aria-pressed')"), "true");
    await new Promise((resolve) => setTimeout(resolve, 1000)); // let noise calibration finish
    await evaluate("window.__micGain.value = 0.2");
    await new Promise((resolve) => setTimeout(resolve, 600));
    await evaluate("window.__micGain.value = 0");
    try {
      await until(() => evaluate("window.__phases.slice(window.__phases.indexOf('listening')).join(',').includes('listening,transcribing,thinking,speaking,listening')"), 12000);
    } catch (error) {
      const detail = await evaluate("JSON.stringify({ phases: window.__phases, status: document.querySelector('#voice-error').textContent, readiness: document.querySelector('#voice-readiness').textContent })");
      throw new Error(`${error.message}: ${detail}; transcriptions=${transcriptions}; speeches=${speeches}`);
    }
    assert.equal(await evaluate("document.querySelector('#heard-question').textContent"), "What problem does Pitchroom AI solve?");
    assert.equal(await evaluate("document.querySelector('#grounding-badge').textContent"), "Grounded in source");
    assert.equal(transcriptions, 1);
    assert.equal(speeches, 0);

    // Interrupt a later reply, then let that new spoken question finish.
    await evaluate("window.__phases = []; window.__ttsDelay = 2000");
    await new Promise((resolve) => setTimeout(resolve, 500));
    await evaluate("window.__micGain.value = 0.2");
    await new Promise((resolve) => setTimeout(resolve, 600));
    await evaluate("window.__micGain.value = 0");
    await until(() => evaluate("document.documentElement.dataset.voicePhase === 'speaking'"));
    await new Promise((resolve) => setTimeout(resolve, 450));
    await evaluate("window.__micGain.value = 0.2");
    await until(() => evaluate("document.querySelector('#stage-message-title').textContent === 'I heard you — keep speaking.'"));
    await evaluate("window.__ttsDelay = 500; window.__micGain.value = 0");
    await until(() => evaluate("window.__phases.join(',').includes('speaking,listening,transcribing,thinking,speaking,listening')"), 12000);
    assert.equal(transcriptions, 3);
    assert.equal(speeches, 0);

    await evaluate("document.querySelector('#live-toggle-stage').click()");
    await until(() => evaluate("document.documentElement.dataset.voicePhase === 'ready'"));
    assert.equal(await evaluate("document.querySelector('#live-toggle-stage').getAttribute('aria-pressed')"), "false");
    assert.equal(await evaluate("window.__micStream.getTracks().every((track) => track.readyState === 'ended')"), true);

    await call("Page.navigate", { url: `http://127.0.0.1:${appPort}/studio` });
    await until(() => evaluate("document.querySelector('#auth-view') && !document.querySelector('#auth-view').hidden"));
    await evaluate(`
      document.querySelector('#register-tab').click();
      document.querySelector('#auth-email').value = 'studio-e2e@example.com';
      document.querySelector('#auth-password').value = 'a-unique-e2e-password';
      document.querySelector('#auth-form').requestSubmit();
    `);
    await until(() => evaluate("!document.querySelector('#studio-view').hidden && document.querySelectorAll('#assistant-list button').length === 1"));
    await evaluate("window.confirm = () => true");
    await call("DOM.enable");
    const documentNode = await call("DOM.getDocument", { depth: -1 });
    const sourceInput = await call("DOM.querySelector", { nodeId: documentNode.root.nodeId, selector: "#source-file" });
    await call("DOM.setFileInputFiles", { nodeId: sourceInput.nodeId, files: [sourcePath] });
    await evaluate("document.querySelector('#source-file').dispatchEvent(new Event('change', { bubbles: true }))");
    await until(() => evaluate("document.querySelectorAll('.source-item').length === 1 && document.querySelector('.source-kind').textContent.includes('Needs review')"));
    await evaluate("document.querySelector('.source-check').click()");
    await until(() => evaluate("document.querySelector('.source-kind').textContent.includes('Approved')"));
    await evaluate("document.querySelector('#voice-question').click()");
    await until(() => evaluate("document.querySelector('#question-message').textContent.includes('type your question')"));
    await evaluate("document.querySelector('#question-input').value = 'How many days are refunds accepted?'; document.querySelector('#question-form').requestSubmit()");
    await until(() => evaluate("document.querySelector('#conversation .message-answer')?.textContent.includes('30 days')"));
    assert.match(await evaluate("document.querySelector('#conversation .evidence-label').textContent"), /Document section/);
    await until(() => evaluate("document.querySelector('#conversation .answer-feedback button')?.textContent === 'Play again'"));
    await evaluate("document.querySelector('#conversation .answer-feedback button').click()");
    await until(() => evaluate("document.querySelector('#conversation .answer-feedback button')?.textContent === 'Play again'"));
    assert.equal(speeches, 2);

    await evaluate("document.querySelector('#publish-assistant').click()");
    await until(() => evaluate("!document.querySelector('#publish-status').hidden"));
    const shareUrl = await evaluate("document.querySelector('#share-url').value");
    await call("Page.navigate", { url: shareUrl });
    await until(() => evaluate("!document.querySelector('#shared-workspace').hidden && document.querySelector('#shared-name').textContent.length > 0"));
    await evaluate("document.querySelector('#shared-question-input').value = 'How many days are refunds accepted?'; document.querySelector('#shared-question-form').requestSubmit()");
    await until(() => evaluate("document.querySelector('#shared-conversation .message-answer')?.textContent.includes('30 days')"));
    await until(() => evaluate("document.querySelector('#shared-conversation .answer-feedback button')?.textContent === 'Play again'"));
    assert.equal(speeches, 3);
    assert.deepEqual(errors, []);
  } finally {
    ws?.close();
    await Promise.all([stop(browser), stop(server)]);
    await rm(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
  }
});
