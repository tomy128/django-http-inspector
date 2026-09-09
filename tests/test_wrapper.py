from django.core.wsgi import get_wsgi_application
from django.test import TestCase

from django_inspect import InspectorWSGI
from django_inspect.models import Exchange
from tests.helpers import call_wsgi, environ


class WrapperTests(TestCase):
    def setUp(self):
        self.app = InspectorWSGI(get_wsgi_application())

    def test_captures_business_request(self):
        result = call_wsgi(self.app, environ("/echo/?x=1", "POST", b"hello"))
        self.assertEqual(result["status"], "200 OK")
        exchange = Exchange.objects.get()
        self.assertEqual(bytes(exchange.request_body), b"hello")
        self.assertEqual(exchange.response_status, 200)
        self.assertEqual(len(bytes(exchange.response_body)), 16)
        self.assertTrue(exchange.response_body_truncated)

    def test_inspector_bypasses_business_app_and_capture(self):
        result = call_wsgi(self.app, environ("/__inspect/"))
        self.assertEqual(result["status"], "200 OK")
        self.assertIn(b"django-inspect", result["body"])
        self.assertEqual(Exchange.objects.count(), 0)

    def test_streaming_response_is_not_preconsumed(self):
        statuses = []
        env = environ("/stream/")
        iterable = self.app(env, lambda status, headers, exc_info=None: statuses.append(status) or (lambda data: None))
        iterator = iter(iterable)
        self.assertEqual(next(iterator), b"first")
        self.assertEqual(Exchange.objects.get().state, "pending")
        self.assertEqual(next(iterator), b"second")
        with self.assertRaises(StopIteration):
            next(iterator)
        self.assertEqual(Exchange.objects.get().state, "complete")
        iterable.close()

    def test_get_without_content_length_is_replayable(self):
        call_wsgi(self.app, environ("/echo/"))
        exchange = Exchange.objects.get()
        self.assertFalse(exchange.request_body_incomplete)
