from django.test import SimpleTestCase

from django_http_inspector.config import load_config
from django_http_inspector.inspector.security import mutation_allowed, request_allowed
from tests.helpers import environ


class SecurityTests(SimpleTestCase):
    def test_loopback_and_allowed_host(self):
        self.assertTrue(request_allowed(environ(), load_config()))
        self.assertFalse(request_allowed(environ(host="evil.test"), load_config()))
        self.assertFalse(request_allowed(environ(remote="10.0.0.2"), load_config()))

    def test_mutation_checks_token_origin_and_fetch_site(self):
        env = environ()
        env.update(HTTP_ORIGIN="http://localhost:8000", HTTP_SEC_FETCH_SITE="same-origin")
        self.assertTrue(mutation_allowed(env, "secret", "secret"))
        env["HTTP_ORIGIN"] = "https://evil.test"
        self.assertFalse(mutation_allowed(env, "secret", "secret"))
