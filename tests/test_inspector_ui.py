from django.core.wsgi import get_wsgi_application
from django.test import SimpleTestCase

from django_http_inspector import InspectorWSGI
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

    def test_clear_requires_token(self):
        result = call_wsgi(self.app, environ("/__inspect/clear", "POST", b"token=wrong"))
        self.assertEqual(result["status"], "403 Forbidden")
        self.assertEqual(self.app.repository.count_exchanges(), 1)

    def test_clear_with_token(self):
        body = f"token={self.app.token}".encode()
        result = call_wsgi(self.app, environ("/__inspect/clear", "POST", body))
        self.assertEqual(result["status"], "303 See Other")
        self.assertEqual(self.app.repository.count_exchanges(), 0)
