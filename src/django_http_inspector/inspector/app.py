from importlib.resources import files
from html import escape
from urllib.parse import parse_qs

from django_http_inspector.inspector.presentation import present_body
from django_http_inspector.inspector.security import mutation_allowed, request_allowed
from django_http_inspector.inspector.templates import render
from django_http_inspector.replay.service import can_replay, replay_exchange
from django_http_inspector.storage.records import ReplayAttemptRecord


STATUS_TEXT = {200: "OK", 302: "Found", 303: "See Other", 400: "Bad Request", 403: "Forbidden", 404: "Not Found", 500: "Internal Server Error"}


class InspectorApp:
    def __init__(self, config, token, repository):
        self.config = config
        self.token = token
        self.repository = repository
        self.base = config.path.rstrip("/")

    def response(self, start_response, content, status=200, content_type="text/html; charset=utf-8", headers=()):
        body = content.encode("utf-8") if isinstance(content, str) else content
        response_headers = [("Content-Type", content_type), ("Content-Length", str(len(body))), *headers]
        start_response(f"{status} {STATUS_TEXT.get(status, '')}".strip(), response_headers)
        return [body]

    def redirect(self, start_response, location):
        return self.response(start_response, b"", 303, headers=(("Location", location),))

    def form(self, environ):
        try:
            length = min(int(environ.get("CONTENT_LENGTH", "0") or 0), 64 * 1024)
        except ValueError:
            length = 0
        return parse_qs(environ["wsgi.input"].read(length).decode("utf-8", "replace"))

    def __call__(self, environ, start_response):
        if not request_allowed(environ, self.config):
            return self.response(start_response, "Inspector access denied.", 403, "text/plain; charset=utf-8")
        path = str(environ.get("PATH_INFO", "/"))
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        relative = path[len(self.base):] or "/"

        if relative.startswith("/assets/") and method == "GET":
            return self.asset(relative, start_response)
        if relative == "/" and method == "GET":
            return self.index(start_response)
        if relative == "/clear" and method == "POST":
            return self.clear(environ, start_response)
        parts = [part for part in relative.split("/") if part]
        if len(parts) == 2 and parts[0] == "requests" and method == "GET":
            return self.detail(parts[1], start_response)
        if len(parts) == 3 and parts[0] == "requests" and parts[2] == "replay" and method == "POST":
            return self.replay(parts[1], environ, start_response)
        return self.response(start_response, "Not found", 404, "text/plain; charset=utf-8")

    def context(self, selected=None, message=""):
        exchanges = self.repository.list_exchanges(limit=200)
        body = body_kind = response_body = response_kind = ""
        attempts = []
        if selected:
            body, body_kind = present_body(selected.request_body, selected.request_content_type)
            response_content_type = next((v for n, v in selected.response_headers if n.lower() == "content-type"), "")
            response_body, response_kind = present_body(selected.response_body, response_content_type)
            attempts = self.repository.list_attempts(selected.id, limit=20)
        return {
            "base": self.base,
            "token": self.token,
            "exchanges": exchanges,
            "selected": selected,
            "request_body": body,
            "request_body_kind": body_kind,
            "response_body": response_body,
            "response_body_kind": response_kind,
            "attempts": attempts,
            "can_replay": bool(selected and can_replay(selected)),
            "message": message,
        }

    def index(self, start_response):
        if not self.repository.available:
            return self.storage_error(start_response)
        try:
            exchanges = self.repository.list_exchanges(limit=1)
            selected = exchanges[0] if exchanges else None
            return self.response(start_response, render("index.html", self.context(selected)))
        except Exception as exc:
            return self.storage_error(start_response, exc)

    def detail(self, exchange_id, start_response, message=""):
        try:
            exchange = self.repository.get_exchange(int(exchange_id))
        except (TypeError, ValueError):
            exchange = None
        except Exception as exc:
            return self.storage_error(start_response, exc)
        if exchange is None:
            return self.response(start_response, "Request not found", 404, "text/plain; charset=utf-8")
        return self.response(start_response, render("index.html", self.context(exchange, message)))

    def clear(self, environ, start_response):
        data = self.form(environ)
        if not mutation_allowed(environ, self.token, data.get("token", [""])[0]):
            return self.response(start_response, "Forbidden", 403, "text/plain; charset=utf-8")
        if not self.repository.available:
            return self.storage_error(start_response)
        try:
            self.repository.clear()
        except Exception as exc:
            return self.storage_error(start_response, exc)
        return self.redirect(start_response, self.base + "/")

    def replay(self, exchange_id, environ, start_response):
        data = self.form(environ)
        if not mutation_allowed(environ, self.token, data.get("token", [""])[0]):
            return self.response(start_response, "Forbidden", 403, "text/plain; charset=utf-8")
        try:
            exchange = self.repository.get_exchange(int(exchange_id))
        except (TypeError, ValueError):
            exchange = None
        except Exception as exc:
            return self.storage_error(start_response, exc)
        if exchange is None:
            return self.response(start_response, "Request not found", 404, "text/plain; charset=utf-8")
        try:
            attempt = replay_exchange(
                exchange, self.config, self.repository, allow_risky=data.get("confirm", [""])[0] == "yes"
            )
        except Exception as exc:
            return self.storage_error(start_response, exc)
        message = "Replay completed." if attempt.state == ReplayAttemptRecord.State.COMPLETE else f"Replay failed: {attempt.error_summary}"
        if attempt.persistence_error:
            message = f"Replay was sent, but its final result could not be saved: {attempt.persistence_error}"
        return self.detail(exchange_id, start_response, message)

    def storage_error(self, start_response, error=None):
        detail = str(error or self.repository.error or "Unknown storage error")
        body = (
            "<!doctype html><html><head><title>Inspector storage unavailable</title></head>"
            "<body><h1>Inspector storage unavailable</h1><p>Business requests continue normally.</p>"
            f"<pre>{escape(detail)}</pre></body></html>"
        )
        return self.response(start_response, body, 500)

    def asset(self, relative, start_response):
        name = relative.rsplit("/", 1)[-1]
        if name not in {"inspect.css", "inspect.js"}:
            return self.response(start_response, "Not found", 404, "text/plain; charset=utf-8")
        data = files("django_http_inspector").joinpath("static", "django_http_inspector", name).read_bytes()
        content_type = "text/css; charset=utf-8" if name.endswith(".css") else "text/javascript; charset=utf-8"
        return self.response(start_response, data, content_type=content_type)
