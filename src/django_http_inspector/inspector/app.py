import hashlib
import json
from html import escape
from importlib.resources import files
from urllib.parse import parse_qs

from django_http_inspector.inspector.presentation import present_body
from django_http_inspector.inspector.security import mutation_allowed, request_allowed
from django_http_inspector.inspector.templates import render
from django_http_inspector.replay.edit import EditValidationError, editable_body, encode_edited_body, headers_to_text, parse_headers
from django_http_inspector.replay.service import can_replay, replay_exchange
from django_http_inspector.storage.records import ReplayAttemptRecord


STATUS_TEXT = {
    200: "OK", 302: "Found", 303: "See Other", 400: "Bad Request", 403: "Forbidden",
    404: "Not Found", 409: "Conflict", 413: "Content Too Large", 500: "Internal Server Error",
}


class PayloadError(ValueError):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


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

    def json_response(self, start_response, payload, status=200):
        return self.response(
            start_response,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            status,
            "application/json; charset=utf-8",
            (("Cache-Control", "no-store"),),
        )

    def redirect(self, start_response, location):
        return self.response(start_response, b"", 303, headers=(("Location", location),))

    def form(self, environ):
        try:
            length = min(int(environ.get("CONTENT_LENGTH", "0") or 0), 64 * 1024)
        except ValueError:
            length = 0
        return parse_qs(environ["wsgi.input"].read(length).decode("utf-8", "replace"))

    def read_json(self, environ):
        limit = self.config.capture_max_bytes + 256 * 1024
        try:
            declared = int(environ.get("CONTENT_LENGTH", "0") or 0)
        except (TypeError, ValueError):
            raise PayloadError(400, "invalid_payload", "Content-Length is invalid.")
        if declared > limit:
            raise PayloadError(413, "payload_too_large", "Edit & Replay payload is too large.")
        content_type = str(environ.get("CONTENT_TYPE", "")).split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise PayloadError(400, "invalid_payload", "Content-Type must be application/json.")
        data = environ["wsgi.input"].read(limit + 1)
        if len(data) > limit:
            raise PayloadError(413, "payload_too_large", "Edit & Replay payload is too large.")
        try:
            payload = json.loads(data.decode("utf-8", "strict"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise PayloadError(400, "invalid_payload", "Request body must be valid UTF-8 JSON.")
        if not isinstance(payload, dict):
            raise PayloadError(400, "invalid_payload", "JSON payload must be an object.")
        allowed = {"token", "headers_text", "body_text"}
        unknown = set(payload) - allowed
        if unknown:
            raise PayloadError(400, "unexpected_field", f"Unexpected field: {sorted(unknown)[0]}.")
        if set(payload) != allowed or not all(isinstance(payload[name], str) for name in allowed):
            raise PayloadError(400, "invalid_payload", "token, headers_text, and body_text are required strings.")
        return payload

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
        if relative == "/api/exchanges" and method == "GET":
            return self.exchange_snapshot(start_response)
        if relative == "/clear" and method == "POST":
            return self.clear(environ, start_response)
        parts = [part for part in relative.split("/") if part]
        if len(parts) == 2 and parts[0] == "requests" and method == "GET":
            return self.detail(parts[1], start_response)
        if len(parts) == 3 and parts[0] == "requests" and parts[2] == "replay" and method == "POST":
            return self.replay(parts[1], environ, start_response)
        if len(parts) == 3 and parts[0] == "requests" and parts[2] == "edit-replay" and method == "POST":
            return self.edit_replay(parts[1], environ, start_response)
        return self.response(start_response, "Not found", 404, "text/plain; charset=utf-8")

    def lightweight_snapshot(self):
        exchanges = self.repository.list_exchanges(limit=200)
        rows = [{
            "id": exchange.id, "method": exchange.method, "path": exchange.path, "state": exchange.state,
            "response_status": exchange.response_status, "duration_ms": exchange.duration_ms,
            "created_at": exchange.created_at.isoformat().replace("+00:00", "Z"),
        } for exchange in exchanges]
        total = self.repository.count_exchanges()
        canonical = json.dumps({"exchanges": rows, "total": total}, sort_keys=True, separators=(",", ":"))
        return rows, total, hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def exchange_snapshot(self, start_response):
        if not self.repository.available:
            return self.json_error(start_response, 500, "storage_unavailable", self.repository.error)
        try:
            rows, total, cursor = self.lightweight_snapshot()
            return self.json_response(start_response, {"cursor": cursor, "exchanges": rows, "total": total})
        except Exception as exc:
            return self.json_error(start_response, 500, "storage_unavailable", str(exc))

    def context(self, selected=None, message=""):
        exchanges = self.repository.list_exchanges(limit=200)
        body = body_kind = response_body = response_kind = ""
        request_parts = response_parts = None
        attempts = []
        edit_allowed = False
        edit_body = edit_reason = ""
        if selected:
            body, body_kind, request_parts = present_body(
                selected.request_body,
                selected.request_content_type,
                complete=not (selected.request_body_truncated or selected.request_body_incomplete),
            )
            response_content_type = next((v for n, v in selected.response_headers if n.lower() == "content-type"), "")
            response_body, response_kind, response_parts = present_body(
                selected.response_body,
                response_content_type,
                complete=not (selected.response_body_truncated or selected.response_body_incomplete),
            )
            attempts = self.repository.list_attempts(selected.id, limit=20)
            edit_allowed, edit_body, edit_reason = editable_body(selected)
        _, total, cursor = self.lightweight_snapshot()
        return {
            "base": self.base, "token": self.token, "exchanges": exchanges, "exchange_total": total,
            "list_cursor": cursor, "selected": selected, "request_body": body, "request_body_kind": body_kind,
            "request_multipart_parts": request_parts, "response_body": response_body,
            "response_body_kind": response_kind, "response_multipart_parts": response_parts, "attempts": attempts,
            "can_replay": bool(selected and can_replay(selected)),
            "can_edit": bool(selected and can_replay(selected) and edit_allowed), "edit_reason": edit_reason,
            "edit_headers": headers_to_text(selected.request_headers) if selected else "", "edit_body": edit_body,
            "message": message,
        }

    def index(self, start_response):
        if not self.repository.available:
            return self.storage_error(start_response)
        try:
            exchanges = self.repository.list_exchanges(limit=1)
            return self.response(start_response, render("index.html", self.context(exchanges[0] if exchanges else None)))
        except Exception as exc:
            return self.storage_error(start_response, exc)

    def detail(self, exchange_id, start_response, message=""):
        try:
            exchange = self.repository.get_exchange(int(exchange_id))
            if exchange is None:
                return self.response(start_response, "Request not found", 404, "text/plain; charset=utf-8")
            return self.response(start_response, render("index.html", self.context(exchange, message)))
        except (TypeError, ValueError):
            return self.response(start_response, "Request not found", 404, "text/plain; charset=utf-8")
        except Exception as exc:
            return self.storage_error(start_response, exc)

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
            attempt = replay_exchange(exchange, self.config, self.repository, allow_risky=True)
        except Exception as exc:
            return self.storage_error(start_response, exc)
        message = "Replay completed." if attempt.state == ReplayAttemptRecord.State.COMPLETE else f"Replay failed: {attempt.error_summary}"
        if attempt.persistence_error:
            qualifier = "may have been sent" if attempt.network_attempted else "was not sent"
            message = f"Replay {qualifier}, but its final result could not be saved: {attempt.persistence_error}"
        return self.detail(exchange_id, start_response, message)

    def edit_replay(self, exchange_id, environ, start_response):
        try:
            payload = self.read_json(environ)
        except PayloadError as exc:
            return self.json_error(start_response, exc.status, exc.code, exc.message)
        if not mutation_allowed(environ, self.token, payload["token"]):
            return self.json_error(start_response, 403, "forbidden", "Forbidden.")
        try:
            exchange = self.repository.get_exchange(int(exchange_id))
        except (TypeError, ValueError):
            exchange = None
        except Exception as exc:
            return self.json_error(start_response, 500, "storage_unavailable", str(exc))
        if exchange is None:
            return self.json_error(start_response, 404, "not_found", "Request not found.")
        allowed, _, reason = editable_body(exchange)
        if not allowed:
            return self.json_error(start_response, 409, "body_not_editable", reason, field="body_text")
        try:
            headers = parse_headers(payload["headers_text"])
            body = encode_edited_body(headers, payload["body_text"])
        except EditValidationError as exc:
            return self.json_error(start_response, exc.status, exc.code, exc.message, field=exc.field, line=exc.line)
        try:
            attempt = replay_exchange(
                exchange, self.config, self.repository, allow_risky=True, headers=headers, body=body, mode="edited"
            )
        except Exception as exc:
            return self.json_error(start_response, 500, "attempt_persistence_failed", str(exc))
        attempt_data = self.attempt_json(attempt)
        if attempt.persistence_error:
            return self.json_error(
                start_response, 500, "outcome_persistence_failed",
                "The replay may have been sent, but its outcome could not be saved.",
                attempt=attempt_data, request_may_have_been_sent=attempt.network_attempted,
            )
        if attempt.state == ReplayAttemptRecord.State.COMPLETE:
            return self.json_response(start_response, {
                "ok": True, "code": "replay_complete", "message": "Replay completed.", "attempt": attempt_data,
            })
        return self.json_response(start_response, {
            "ok": False, "code": "replay_failed", "message": f"Replay failed: {attempt.error_summary}",
            "attempt": attempt_data,
        })

    @staticmethod
    def attempt_json(attempt):
        return {
            "id": attempt.id, "mode": attempt.mode, "state": attempt.state,
            "response_status": attempt.response_status, "error_stage": attempt.error_stage,
            "error_summary": attempt.error_summary,
        }

    def json_error(self, start_response, status, code, message, **extra):
        payload = {"ok": False, "code": code, "message": message, "request_may_have_been_sent": False}
        payload.update({key: value for key, value in extra.items() if value is not None})
        return self.json_response(start_response, payload, status)

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
