# django-http-inspector

django-http-inspector is an embedded HTTP traffic inspector for Django development. It captures requests and responses outside the project's middleware chain and can replay a captured request to the URL seen at capture time over a real HTTP connection.

It is a development tool, not a reverse proxy, tunnel, production observability platform, or production security boundary.

## Installation

```bash
python -m pip install django-http-inspector
```

## Intended integration

```python
# wsgi.py
from django.core.wsgi import get_wsgi_application
from django_http_inspector import InspectorWSGI

application = InspectorWSGI(get_wsgi_application())
```

```bash
python manage.py runserver
```

Open `http://127.0.0.1:8000/__inspect/`.

## Configuration

```python
DJANGO_HTTP_INSPECTOR = {
    "ENABLED": DEBUG,
    # Set True only on a trusted development network. No authentication is added.
    "ALLOW_REMOTE": False,
    "PATH": "/__inspect/",
    "CAPTURE_MAX_BYTES": 1024 * 1024,
    "MAX_RECORDS": 1000,
    "EXCLUDE_PATHS": [
        "/static/",
        "/favicon.ico",
        "/.well-known/appspecific/com.chrome.devtools.json",
    ],
    "TRUSTED_PROXY_CIDRS": [],
    "INSPECTOR_ALLOWED_HOSTS": ["localhost", "127.0.0.1", "[::1]"],
    "REPLAY_TIMEOUT": 10,
    # Default: BASE_DIR / ".django-http-inspector.sqlite3"
    "SQLITE_PATH": BASE_DIR / ".django-http-inspector.sqlite3",
}
```

django-http-inspector is disabled by default when `DEBUG=False`. The MVP Inspector UI is loopback-only.

To access Inspector from another device during development, use the single explicit switch and make Django listen on the network:

```python
DJANGO_HTTP_INSPECTOR = {
    "ALLOW_REMOTE": True,
}
```

```bash
python manage.py runserver 0.0.0.0:8000
```

Then open `http://<development-machine-ip>:8000/__inspect/`. Remote mode has no authentication: anyone who can connect can read captured credentials and bodies and trigger real Replay requests. Never expose it to the public internet or an untrusted network. The advanced `INSPECTOR_ALLOWED_HOSTS` and `INSPECTOR_ALLOWED_CLIENT_CIDRS` settings remain available for the default local-only mode but are not needed when `ALLOW_REMOTE=True`.

Inspector records live in a package-managed SQLite database, not in Django's business database. You do not need to add the package to `INSTALLED_APPS` or run migrations. The file survives `runserver` reloads; delete it to reset all Inspector history.

Add the runtime files to the project's `.gitignore`:

```gitignore
.django-http-inspector.sqlite3
.django-http-inspector.sqlite3-shm
.django-http-inspector.sqlite3-wal
```

## Replay semantics

Replay makes a real HTTP request to the complete URL reconstructed when the original request was captured. It does not substitute a loopback URL and does not call the Django handler in-process. Consequently, it can pass through DNS, TLS, a public tunnel, a gateway, the web server, and the complete Django middleware chain again.

WSGI servers normalize request data before applications see it. django-http-inspector therefore provides a semantically equivalent replay of the WSGI-observable request, not a byte-for-byte recreation of the network stream. Hop-by-hop headers are removed, `Host` and `Content-Length` are regenerated, and a correlation header is added.

Replay causes real side effects. Treat payment, email, webhook, and mutation endpoints accordingly.

The request stream refreshes automatically while the Inspector tab is visible. Select **Edit & Replay** to change a replay copy's headers and textual body. The captured method and complete URL remain read-only and are always used as the replay target; binary, multipart, and incomplete bodies cannot be edited. Duplicate headers are supported in the raw `Name: Value` editor.

Complete `multipart/form-data` bodies are presented as ordered form fields. File parts show only their filename, media type, and captured-content size; binary file bytes are never rendered. Malformed, incomplete, or oversized multipart previews safely fall back to the existing raw/binary view. This presentation does not modify the bytes saved or sent by Replay.

Chrome DevTools may request `/.well-known/appspecific/com.chrome.devtools.json` while inspecting localhost. The default exclusions prevent that harmless discovery request from cluttering Inspector, although Django may still log its 404 response.

## Development

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python tests/runtests.py
.venv/bin/python -m build
```

See the [approved design](docs/superpowers/specs/2026-09-09-django-http-inspector-mvp-design.md) for replay semantics and security boundaries.
