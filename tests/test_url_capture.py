from django.test import SimpleTestCase

from django_inspect.capture.url import build_url
from tests.helpers import environ


class UrlCaptureTests(SimpleTestCase):
    def test_direct_url_preserves_query(self):
        env = environ("/echo/?value=a%2Fb&empty=")
        url, scheme, host, provenance = build_url(env)
        self.assertEqual(url, "http://localhost:8000/echo/?value=a%2Fb&empty=")
        self.assertEqual(provenance, "reconstructed")

    def test_only_trusts_proxy_header_from_configured_cidr(self):
        env = environ("/hook")
        env.update(HTTP_X_FORWARDED_PROTO="https", HTTP_X_FORWARDED_HOST="public.example")
        self.assertEqual(build_url(env)[0], "http://localhost:8000/hook")
        self.assertEqual(build_url(env, ("127.0.0.0/8",))[0], "https://public.example/hook")

    def test_rejects_invalid_host(self):
        env = environ(host="bad@example.com")
        self.assertEqual(build_url(env)[0], "")
