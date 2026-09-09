import io
import tempfile
from pathlib import Path

from django.test import override_settings


def environ(path="/echo/", method="GET", body=b"", host="localhost:8000", remote="127.0.0.1"):
    path_info, _, query = path.partition("?")
    return {
        "REQUEST_METHOD": method,
        "SCRIPT_NAME": "",
        "PATH_INFO": path_info,
        "QUERY_STRING": query,
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "8000",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "HTTP_HOST": host,
        "REMOTE_ADDR": remote,
        "CONTENT_LENGTH": str(len(body)) if body else "",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "http",
        "wsgi.input": io.BytesIO(body),
        "wsgi.errors": io.StringIO(),
        "wsgi.multithread": True,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
    }


def call_wsgi(app, env):
    result = {}

    def start_response(status, headers, exc_info=None):
        result["status"] = status
        result["headers"] = headers
        return lambda data: result.setdefault("written", []).append(data)

    iterable = app(env, start_response)
    try:
        result["body"] = b"".join(iterable)
    finally:
        close = getattr(iterable, "close", None)
        if close:
            close()
    return result


class IsolatedStorageMixin:
    def setUp(self):
        super().setUp()
        self.storage_directory = tempfile.TemporaryDirectory(prefix="django-http-inspector-case-")
        self.storage_path = Path(self.storage_directory.name) / "inspector.sqlite3"
        self.settings_override = override_settings(
            DJANGO_HTTP_INSPECTOR={
                "ENABLED": True,
                "CAPTURE_MAX_BYTES": 16,
                "MAX_RECORDS": 100,
                "SQLITE_PATH": self.storage_path,
            }
        )
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        self.storage_directory.cleanup()
        super().tearDown()
