export default {
  async fetch(request, env) {
    let backend;
    try {
      backend = new URL(env.BACKEND_URL);
      if (backend.protocol !== "https:" || backend.username || backend.password ||
          backend.pathname !== "/" || backend.search || backend.hash) throw new Error();
    } catch {
      return new Response("The demo gateway needs a valid HTTPS BACKEND_URL.", { status: 503 });
    }

    const incoming = new URL(request.url);
    if (backend.origin === incoming.origin) {
      return new Response("The demo gateway cannot point to itself.", { status: 503 });
    }
    backend.pathname = incoming.pathname;
    backend.search = incoming.search;
    const upstream = new Request(backend, request);
    upstream.headers.delete("host");
    try {
      const response = await fetch(upstream, { redirect: "manual" });
      const location = response.headers.get("location");
      if (location) {
        const redirect = new URL(location, backend);
        if (redirect.origin === backend.origin) {
          const headers = new Headers(response.headers);
          headers.set("location", incoming.origin + redirect.pathname + redirect.search + redirect.hash);
          return new Response(response.body, { status: response.status, headers });
        }
      }
      return response;
    } catch {
      return new Response("The demo is temporarily offline. Please try again shortly.", {
        status: 503,
        headers: { "Retry-After": "30", "Cache-Control": "no-store" },
      });
    }
  },
};
