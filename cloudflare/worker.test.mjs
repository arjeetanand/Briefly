import assert from "node:assert/strict";
import { test } from "node:test";
import worker from "./worker.mjs";

const env = { BACKEND_URL: "https://demo.trycloudflare.com" };

test("forwards upload bytes, query and authorization to the configured backend", async (t) => {
  const form = new FormData();
  form.append("file", new Blob(["demo document"]), "demo.txt");
  const request = new Request("https://pitchroom.example/api/pitch/file?mode=demo", {
    method: "POST", headers: { Authorization: "Bearer test-token" }, body: form,
  });
  t.mock.method(globalThis, "fetch", async (upstream, options) => {
    assert.equal(upstream.url, "https://demo.trycloudflare.com/api/pitch/file?mode=demo");
    assert.equal(upstream.method, "POST");
    assert.equal(upstream.headers.get("authorization"), "Bearer test-token");
    assert.equal(upstream.headers.get("host"), null);
    assert.equal(options.redirect, "manual");
    const uploaded = await upstream.formData();
    assert.equal(await uploaded.get("file").text(), "demo document");
    return new Response("audio", { headers: { "Content-Type": "audio/wav" } });
  });
  const response = await worker.fetch(request, env);
  assert.equal(response.headers.get("content-type"), "audio/wav");
  assert.equal(await response.text(), "audio");
});

test("keeps backend redirects on the fixed public hostname", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response(null, {
    status: 307, headers: { Location: "https://demo.trycloudflare.com/docs/?q=1#top" },
  }));
  const response = await worker.fetch(new Request("https://pitchroom.example/docs"), env);
  assert.equal(response.status, 307);
  assert.equal(response.headers.get("location"), "https://pitchroom.example/docs/?q=1#top");
});

test("rejects invalid configuration and loops without forwarding", async (t) => {
  t.mock.method(globalThis, "fetch", () => assert.fail("Must not forward"));
  for (const url of [undefined, "http://localhost:8502", "https://user:pass@example.com",
    "https://example.com/path", "https://example.com/?q=1", "https://example.com/#hash",
    "https://pitchroom.example"]) {
    const response = await worker.fetch(new Request("https://pitchroom.example/"), { BACKEND_URL: url });
    assert.equal(response.status, 503);
  }
});

test("shows an uncached offline response when the tunnel is unreachable", async (t) => {
  t.mock.method(globalThis, "fetch", async () => { throw new Error("private connection details"); });
  const response = await worker.fetch(new Request("https://pitchroom.example/"), env);
  assert.equal(response.status, 503);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(response.headers.get("retry-after"), "30");
  assert.doesNotMatch(await response.text(), /private/);
});
