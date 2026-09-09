# Architecture

django-inspect wraps the project's WSGI application. It routes `/__inspect/*` to a small package-owned WSGI application before Django's middleware and sends every other request directly to the original Django application.

```text
WSGI server
  ↓
InspectorWSGI
  ├── /__inspect/* → InspectorApp
  └── business path → capture → Django WSGI application
```

Normal traffic is not proxied. The request input and response iterable are wrapped with bounded tee implementations so traffic continues lazily while a limited copy is persisted through Django ORM.

Outbound replay is modeled separately from inbound traffic:

- `Exchange` describes an inbound request and its application response.
- `ReplayAttempt` describes an outbound replay, including the sent snapshot, response or failure, selected peer address, and optional observed inbound exchange.

This separation retains DNS/TLS/connect/timeout failures even when the request never returns to this Django process.

The WSGI implementation is deliberately first. ASGI support will share configuration, presentation, persistence, and replay services only after those boundaries have proven stable.
