from django.core.wsgi import get_wsgi_application
import json
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from django_http_inspector import InspectorWSGI
from django_http_inspector.storage.records import ReplayAttemptRecord
from tests.helpers import IsolatedStorageMixin, call_wsgi, environ


class InspectorUITests(IsolatedStorageMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.app = InspectorWSGI(get_wsgi_application())
        self.exchange = self.app.repository.create_exchange(
            method="POST", path="/webhook", url="https://example.test/webhook",
            request_headers=[["Content-Type", "application/json"]], request_body=b'{"ok": true}',
            request_content_type="application/json", response_status=200, response_body=b"done",
        )

    def test_detail_escapes_untrusted_content(self):
        self.exchange.path = "<script>alert(1)</script>"
        self.app.repository.update_exchange(self.exchange)
        result = call_wsgi(self.app, environ(f"/__inspect/requests/{self.exchange.id}/"))
        self.assertEqual(result["status"], "200 OK")
        self.assertNotIn(b"<script>alert", result["body"])
        self.assertIn(b"&lt;script&gt;", result["body"])

    def test_detail_has_direct_replay_warning_live_list_and_edit_fields(self):
        result = call_wsgi(self.app, environ(f"/__inspect/requests/{self.exchange.id}/"))
        self.assertIn(b"Replay sends a real request and may cause side effects.", result["body"])
        self.assertNotIn(b'type="checkbox"', result["body"])
        self.assertIn(b"data-live-state", result["body"])
        self.assertIn(b"data-edit-headers", result["body"])
        self.assertIn(b"data-edit-body", result["body"])
        self.assertIn(b">POST<", result["body"])
        self.assertIn(b"https://example.test/webhook", result["body"])

    def test_exchange_snapshot_is_lightweight_and_not_cached(self):
        result = call_wsgi(self.app, environ("/__inspect/api/exchanges"))
        payload = json.loads(result["body"])
        self.assertEqual(result["status"], "200 OK")
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["exchanges"][0]["id"], self.exchange.id)
        self.assertNotIn("request_body", payload["exchanges"][0])
        self.assertIn(("Cache-Control", "no-store"), result["headers"])

    def edit_environ(self, payload):
        body = json.dumps(payload).encode()
        env = environ(f"/__inspect/requests/{self.exchange.id}/edit-replay", "POST", body)
        env["CONTENT_TYPE"] = "application/json"
        return env

    def remote_app(self):
        configured = {**settings.DJANGO_HTTP_INSPECTOR, "ALLOW_REMOTE": True}
        context = override_settings(DJANGO_HTTP_INSPECTOR=configured)
        context.enable()
        self.addCleanup(context.disable)
        return InspectorWSGI(get_wsgi_application())

    def test_remote_mode_exposes_index_asset_and_api_but_default_rejects_them(self):
        paths = ("/__inspect/", "/__inspect/assets/inspect.js", "/__inspect/api/exchanges")
        for path in paths:
            with self.subTest(default_path=path):
                result = call_wsgi(self.app, environ(path, host="unlisted.test", remote="203.0.113.8"))
                self.assertEqual(result["status"], "403 Forbidden")
        app = self.remote_app()
        for path in paths:
            with self.subTest(remote_path=path):
                result = call_wsgi(app, environ(path, host="unlisted.test", remote="203.0.113.8"))
                self.assertEqual(result["status"], "200 OK")

    def test_remote_mode_does_not_bypass_mutation_guards(self):
        app = self.remote_app()
        exchange = app.repository.create_exchange(
            method="POST", path="/hook", url="https://example.test/hook",
            request_headers=[["Content-Type", "text/plain"]], request_body=b"body",
            request_content_type="text/plain",
        )
        json_payload = lambda token: json.dumps({"token": token, "headers_text": "Content-Type: text/plain", "body_text": "body"}).encode()
        cases = [
            ("/__inspect/clear", b"token=wrong", "application/x-www-form-urlencoded"),
            (f"/__inspect/requests/{exchange.id}/replay", b"token=wrong", "application/x-www-form-urlencoded"),
            (f"/__inspect/requests/{exchange.id}/edit-replay", json_payload("wrong"), "application/json"),
        ]
        for path, body, content_type in cases:
            for header, value in (("wrong_token", None), ("HTTP_ORIGIN", "https://evil.test"), ("HTTP_SEC_FETCH_SITE", "cross-site")):
                with self.subTest(path=path, rejected_by=header):
                    accepted_body = body if header == "wrong_token" else (
                        json_payload(app.token) if content_type == "application/json" else f"token={app.token}".encode()
                    )
                    env = environ(path, "POST", accepted_body, host="remote.test", remote="203.0.113.8")
                    env["CONTENT_TYPE"] = content_type
                    if value is not None:
                        env[header] = value
                    self.assertEqual(call_wsgi(app, env)["status"], "403 Forbidden")

        with patch("django_http_inspector.inspector.app.replay_exchange") as replay:
            replay.return_value = ReplayAttemptRecord(id=9, state=ReplayAttemptRecord.State.COMPLETE)
            normal = environ(f"/__inspect/requests/{exchange.id}/replay", "POST", f"token={app.token}".encode(), host="remote.test", remote="203.0.113.8")
            normal.update(HTTP_ORIGIN="http://remote.test", HTTP_SEC_FETCH_SITE="same-origin")
            self.assertEqual(call_wsgi(app, normal)["status"], "200 OK")
            edited = environ(f"/__inspect/requests/{exchange.id}/edit-replay", "POST", json_payload(app.token), host="remote.test", remote="203.0.113.8")
            edited.update(CONTENT_TYPE="application/json", HTTP_SEC_FETCH_SITE="none")
            self.assertEqual(call_wsgi(app, edited)["status"], "200 OK")

        clear = environ("/__inspect/clear", "POST", f"token={app.token}".encode(), host="remote.test", remote="203.0.113.8")
        clear.update(HTTP_ORIGIN="http://remote.test", HTTP_SEC_FETCH_SITE="same-origin")
        self.assertEqual(call_wsgi(app, clear)["status"], "303 See Other")

    @patch("django_http_inspector.inspector.app.replay_exchange")
    def test_edit_replay_uses_original_target_with_edited_snapshot(self, replay):
        replay.return_value = ReplayAttemptRecord(id=7, mode="edited", state=ReplayAttemptRecord.State.COMPLETE)
        payload = {"token": self.app.token, "headers_text": "Content-Type: text/plain\nX-Test: edited", "body_text": "new"}
        result = call_wsgi(self.app, self.edit_environ(payload))
        response = json.loads(result["body"])
        self.assertEqual(result["status"], "200 OK")
        self.assertTrue(response["ok"])
        args, kwargs = replay.call_args
        self.assertEqual(args[0].method, "POST")
        self.assertEqual(args[0].url, "https://example.test/webhook")
        self.assertEqual(kwargs["headers"], [["Content-Type", "text/plain"], ["X-Test", "edited"]])
        self.assertEqual(kwargs["body"], b"new")
        self.assertEqual(kwargs["mode"], "edited")
        self.assertTrue(kwargs["allow_risky"])

    @patch("django_http_inspector.inspector.app.replay_exchange")
    def test_edit_replay_rejects_method_or_url_fields_before_attempt(self, replay):
        payload = {"token": self.app.token, "headers_text": "", "body_text": "", "method": "DELETE"}
        result = call_wsgi(self.app, self.edit_environ(payload))
        self.assertEqual(result["status"], "400 Bad Request")
        self.assertEqual(json.loads(result["body"])["code"], "unexpected_field")
        replay.assert_not_called()

    @patch("django_http_inspector.inspector.app.replay_exchange")
    def test_binary_body_edit_is_rejected(self, replay):
        self.exchange.request_body = b"\x00"
        self.exchange.request_content_type = "application/octet-stream"
        self.app.repository.update_exchange(self.exchange)
        payload = {"token": self.app.token, "headers_text": "Content-Type: application/octet-stream", "body_text": ""}
        result = call_wsgi(self.app, self.edit_environ(payload))
        self.assertEqual(result["status"], "409 Conflict")
        self.assertEqual(json.loads(result["body"])["field"], "body_text")
        replay.assert_not_called()

    def test_clear_requires_token(self):
        result = call_wsgi(self.app, environ("/__inspect/clear", "POST", b"token=wrong"))
        self.assertEqual(result["status"], "403 Forbidden")
        self.assertEqual(self.app.repository.count_exchanges(), 1)

    def test_clear_with_token(self):
        body = f"token={self.app.token}".encode()
        result = call_wsgi(self.app, environ("/__inspect/clear", "POST", body))
        self.assertEqual(result["status"], "303 See Other")
        self.assertEqual(self.app.repository.count_exchanges(), 0)
