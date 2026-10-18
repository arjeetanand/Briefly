# Fixed Pitchroom demo link

Public link: https://pitchroom-gateway.arjeet-anand2024.workers.dev

The Worker forwards the frontend, uploads, and voice API to the current tunnel.
Visitors use the Worker's fixed `workers.dev` URL. The local app and tunnel must
stay running; this gateway does not host the Python backend or speech models.

## Deploy

From the project root, with a Cloudflare account:

```bash
npx wrangler login
npx wrangler deploy --config cloudflare/wrangler.toml
```

Alternatively, create a Worker named `pitchroom-gateway` in Cloudflare's
dashboard, paste `worker.mjs` into its editor, and set the text variable
`BACKEND_URL` to your current HTTPS tunnel origin (no path).

## When the tunnel link changes

Open **Workers & Pages → pitchroom-gateway → Settings → Variables and Secrets**.
Edit the text variable `BACKEND_URL` to the new `https://….trycloudflare.com`
origin and deploy the change. The public Worker URL stays the same.

For CLI updates, edit `BACKEND_URL` in `wrangler.toml` and run the deploy command.
An explicitly configured value in this file takes precedence over dashboard
edits on deployment, so keep it aligned when deploying from the CLI.

No provider secrets or root `.env` files belong in this Worker. The Python API
retains its existing access-token behavior and shared document state; use only
non-sensitive demo documents. The separate MCP endpoint has its own hostname
allowlist and is not configured for this gateway.

Check the gateway logic with `node --test cloudflare/worker.test.mjs`.
