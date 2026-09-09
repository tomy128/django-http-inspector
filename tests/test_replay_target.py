from unittest.mock import patch

from django.test import SimpleTestCase

from django_http_inspector.replay.target import TargetError, resolve_target


class ReplayTargetTests(SimpleTestCase):
    @patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("203.0.113.10", 443))])
    def test_preserves_target(self, _lookup):
        target = resolve_target("https://example.test:8443/a/b?x=a%2Fb")
        self.assertEqual(target.hostname, "example.test")
        self.assertEqual(target.port, 8443)
        self.assertEqual(target.request_target, "/a/b?x=a%2Fb")

    def test_rejects_userinfo(self):
        with self.assertRaises(TargetError):
            resolve_target("http://user:pass@example.test/")
