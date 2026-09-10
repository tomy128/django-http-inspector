# Architecture

django-http-inspector wraps the project's WSGI application. It routes `/__inspect/*` to a small package-owned WSGI application before Django's middleware and sends every other request directly to the original Django application.

Inspector access is local-only by default and checks both Host and client CIDR. The explicit `ALLOW_REMOTE=True` development mode bypasses those two read-access checks so any client able to reach the server can use the package-owned UI and API. It does not change business routing, mutation request-forgery checks, or replay target handling.

```text
WSGI server
  ↓
InspectorWSGI
  ├── /__inspect/* → InspectorApp
  └── business path → capture → Django WSGI application
```

Normal traffic is not proxied. The request input and response iterable are wrapped with bounded tee implementations so traffic continues lazily while a limited copy is persisted through a package-owned SQLite repository.

The repository defaults to `BASE_DIR/.django-http-inspector.sqlite3`, creates and versions its own schema, and uses short-lived connections with bounded lock waits. It never uses Django's configured business databases. Package templates are loaded through an independent template engine, so neither `INSTALLED_APPS`, a project template backend, nor Django migrations are required.

Outbound replay is modeled separately from inbound traffic:

- `Exchange` describes an inbound request and its application response.
- `ReplayAttempt` describes an outbound replay, including the sent snapshot, response or failure, selected peer address, and optional observed inbound exchange.

Equivalent replay snapshots the captured headers and body. Edit & Replay accepts only a validated raw header list and textual body, then stores those edited values in an attempt with `mode="edited"`; method and URL are always loaded from the source Exchange. A lightweight JSON endpoint returns the latest 200 request summaries for the browser's visibility-aware polling loop, without transferring captured headers or bodies.

This separation retains DNS/TLS/connect/timeout failures even when the request never returns to this Django process.

A pending replay attempt must commit before any network operation. The inbound correlation claim and Exchange association commit atomically. Capture storage errors are logged without changing the business response; an unavailable repository leaves business traffic running and gives the isolated Inspector UI its own diagnostic response.

The WSGI implementation is deliberately first. ASGI support will share configuration, presentation, persistence, and replay services only after those boundaries have proven stable.
