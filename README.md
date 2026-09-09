# django-inspect

django-inspect is an embedded HTTP traffic inspector for Django development. It captures requests and responses outside the project's middleware chain and can replay a captured request to the URL seen at capture time over a real HTTP connection.

It is a development tool, not a reverse proxy, tunnel, production observability platform, or production security boundary.

## Intended integration

```python
# settings.py
INSTALLED_APPS += ["django_inspect"]
```

```python
# wsgi.py
from django.core.wsgi import get_wsgi_application
from django_inspect import InspectorWSGI

application = InspectorWSGI(get_wsgi_application())
```

```bash
python manage.py migrate
python manage.py runserver
```

Open `http://127.0.0.1:8000/__inspect/`.

## Configuration

```python
DJANGO_INSPECT = {
    "ENABLED": DEBUG,
    "PATH": "/__inspect/",
    "CAPTURE_MAX_BYTES": 1024 * 1024,
    "MAX_RECORDS": 1000,
    "EXCLUDE_PATHS": ["/static/", "/favicon.ico"],
    "TRUSTED_PROXY_CIDRS": [],
    "INSPECTOR_ALLOWED_HOSTS": ["localhost", "127.0.0.1", "[::1]"],
    "REPLAY_TIMEOUT": 10,
}
```

django-inspect is disabled by default when `DEBUG=False`. The MVP Inspector UI is loopback-only.

## Replay semantics

Replay makes a real HTTP request to the complete URL reconstructed when the original request was captured. It does not substitute a loopback URL and does not call the Django handler in-process. Consequently, it can pass through DNS, TLS, a public tunnel, a gateway, the web server, and the complete Django middleware chain again.

WSGI servers normalize request data before applications see it. django-inspect therefore provides a semantically equivalent replay of the WSGI-observable request, not a byte-for-byte recreation of the network stream. Hop-by-hop headers are removed, `Host` and `Content-Length` are regenerated, and a correlation header is added.

Replay causes real side effects. Treat payment, email, webhook, and mutation endpoints accordingly.

## Development

```bash
python -m venv .venv
.venv/bin/python -m pip install -e . build
.venv/bin/python tests/runtests.py
.venv/bin/python -m build
```

See the [approved design](docs/superpowers/specs/2026-09-09-django-inspect-mvp-design.md) for replay semantics and security boundaries.
