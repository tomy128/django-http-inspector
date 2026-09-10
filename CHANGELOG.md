# Changelog

## 0.1.5 - 2026-09-10

- Publish version tags through a least-privilege GitHub Actions workflow that builds distributions once, uploads them to PyPI with Trusted Publishing, and creates a GitHub Release from the same verified artifact.
- Validate tag/version equality, package contents, fresh-wheel installation, and SHA-256 checksums before irreversible publishing steps.

## 0.1.4 - 2026-09-10

- Present complete multipart/form-data bodies as ordered fields and file metadata without rendering binary file contents.
- Exclude Chrome DevTools automatic-workspace discovery requests from capture by default.
- Rename the request editing action to `Edit & Replay`.

## 0.1.3 - 2026-09-10

- Add a single `ALLOW_REMOTE=True` switch for unauthenticated Inspector access from any client that can reach the development server.
- Keep local-only access as the default and emit a clear warning when remote access is enabled.
- Preserve the existing advanced Host and client CIDR configuration for local-only mode.

## 0.1.2 - 2026-09-09

- Remove the per-replay acknowledgement checkbox and keep the side-effect warning beside the action.
- Refresh the request stream automatically with visibility-aware retry behavior while preserving the selected detail and edit draft.
- Add Edit & Replay for raw headers and textual bodies while keeping the captured method and URL immutable.

## 0.1.1 - 2026-09-09

- Store captured traffic in a package-managed project SQLite file by default.
- Require neither `INSTALLED_APPS` nor Django migrations, and preserve history across `runserver` reloads without touching business databases.

## 0.1.0 - 2026-09-09

- Add WSGI request and response capture with bounded bodies.
- Add isolated `/__inspect/` request stream and detail UI.
- Add real HTTP replay to the captured effective URL.
- Add persistent replay attempts and inbound correlation.
- Add loopback, Host, request-forgery, URL, and pinned-DNS safeguards.
