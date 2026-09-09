from django.core.wsgi import get_wsgi_application
from django.test import SimpleTestCase
from django.test import override_settings
import sqlite3
import warnings

from django_http_inspector import InspectorWSGI
from tests.helpers import IsolatedStorageMixin, call_wsgi, environ


class WrapperTests(IsolatedStorageMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.app = InspectorWSGI(get_wsgi_application())

    def test_captures_business_request(self):
        result = call_wsgi(self.app, environ("/echo/?x=1", "POST", b"hello"))
        self.assertEqual(result["status"], "200 OK")
        exchange = self.app.repository.list_exchanges()[0]
        self.assertEqual(bytes(exchange.request_body), b"hello")
        self.assertEqual(exchange.response_status, 200)
        self.assertEqual(len(bytes(exchange.response_body)), 16)
        self.assertTrue(exchange.response_body_truncated)

    def test_inspector_bypasses_business_app_and_capture(self):
        result = call_wsgi(self.app, environ("/__inspect/"))
        self.assertEqual(result["status"], "200 OK")
        self.assertIn(b"django-http-inspector", result["body"])
        self.assertEqual(self.app.repository.count_exchanges(), 0)

    def test_streaming_response_is_not_preconsumed(self):
        statuses = []
        env = environ("/stream/")
        iterable = self.app(env, lambda status, headers, exc_info=None: statuses.append(status) or (lambda data: None))
        iterator = iter(iterable)
        self.assertEqual(next(iterator), b"first")
        self.assertEqual(self.app.repository.list_exchanges()[0].state, "pending")
        self.assertEqual(next(iterator), b"second")
        with self.assertRaises(StopIteration):
            next(iterator)
        self.assertEqual(self.app.repository.list_exchanges()[0].state, "complete")
        iterable.close()

    def test_get_without_content_length_is_replayable(self):
        call_wsgi(self.app, environ("/echo/"))
        exchange = self.app.repository.list_exchanges()[0]
        self.assertFalse(exchange.request_body_incomplete)

    def test_unavailable_storage_does_not_block_business_requests(self):
        bad_path = self.storage_path.parent / "newer.sqlite3"
        connection = sqlite3.connect(bad_path)
        connection.execute("PRAGMA user_version=99")
        connection.close()
        with override_settings(DJANGO_HTTP_INSPECTOR={"ENABLED": True, "SQLITE_PATH": bad_path}):
            with self.assertLogs("django_http_inspector", level="ERROR"):
                app = InspectorWSGI(get_wsgi_application())
            self.assertFalse(app.repository.available)
            self.assertEqual(call_wsgi(app, environ("/echo/"))["status"], "200 OK")
            result = call_wsgi(app, environ("/__inspect/"))
            self.assertEqual(result["status"], "500 Internal Server Error")
            self.assertIn(b"storage unavailable", result["body"])

    def test_capture_does_not_create_or_open_business_database(self):
        business_path = self.storage_path.parent / "business.sqlite3"

        def business_app(_environ, start_response):
            start_response("204 No Content", [])
            return [b""]

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with override_settings(
                DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": business_path}}
            ):
                app = InspectorWSGI(business_app)
                result = call_wsgi(app, environ("/business/"))
        self.assertEqual(result["status"], "204 No Content")
        self.assertFalse(business_path.exists())
