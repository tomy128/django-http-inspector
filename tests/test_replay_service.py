from unittest.mock import patch

from django.test import TestCase

from django_inspect.config import load_config
from django_inspect.models import Exchange, ReplayAttempt
from django_inspect.replay.service import replay_exchange
from django_inspect.replay.target import ReplayTarget
from django_inspect.replay.transport import ReplayTransportError


class ReplayServiceTests(TestCase):
    def source(self, **changes):
        values = {
            "method": "POST", "path": "/hook", "url": "https://example.test/hook",
            "request_headers": [], "request_body": b"body", "request_declared_size": 4,
            "request_observed_size": 4, "request_captured_size": 4,
        }
        values.update(changes)
        return Exchange.objects.create(**values)

    def test_incomplete_request_creates_persistent_failure(self):
        attempt = replay_exchange(self.source(request_body_incomplete=True), load_config())
        self.assertEqual(attempt.state, ReplayAttempt.State.ERROR)
        self.assertEqual(attempt.error_stage, "validation")

    @patch("django_inspect.replay.service.resolve_target")
    @patch("django_inspect.replay.service.send_request", side_effect=ReplayTransportError("timeout", "timed out"))
    def test_network_failure_is_persisted(self, _send, resolve):
        resolve.return_value = ReplayTarget("https://example.test/hook", "https", "example.test", 443, "/hook", ("93.184.216.34",), False)
        attempt = replay_exchange(self.source(), load_config())
        self.assertEqual(attempt.state, ReplayAttempt.State.ERROR)
        self.assertEqual(attempt.error_stage, "timeout")
        self.assertEqual(attempt.error_summary, "timed out")
