# Changelog

## 0.1.0 - 2026-09-09

- Add WSGI request and response capture with bounded bodies.
- Add isolated `/__inspect/` request stream and detail UI.
- Add real HTTP replay to the captured effective URL.
- Add persistent replay attempts and inbound correlation.
- Add loopback, Host, request-forgery, URL, and pinned-DNS safeguards.
- Store captured traffic in a package-managed project SQLite file by default.
- Require neither `INSTALLED_APPS` nor Django migrations, and preserve history across `runserver` reloads without touching business databases.
