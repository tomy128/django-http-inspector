from unittest.mock import patch

from django.test import SimpleTestCase

from django_http_inspector.config import load_config
from django_http_inspector.replay.service import replay_exchange
from django_http_inspector.replay.target import ReplayTarget
from django_http_inspector.replay.transport import ReplayTransportError
from django_http_inspector.storage import InspectorRepository
from django_http_inspector.storage.records import ReplayAttemptRecord
from tests.helpers import IsolatedStorageMixin


class ReplayServiceTests(IsolatedStorageMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.repository = InspectorRepository(self.storage_path)

    def source(self, **changes):
        values = {
            "method": "POST", "path": "/hook", "url": "https://example.test/hook",
            "request_headers": [], "request_body": b"body", "request_declared_size": 4,
            "request_observed_size": 4, "request_captured_size": 4,
        }
        values.update(changes)
        return self.repository.create_exchange(**values)

    def test_incomplete_request_creates_persistent_failure(self):
        attempt = replay_exchange(self.source(request_body_incomplete=True), load_config(), self.repository)
        self.assertEqual(attempt.state, ReplayAttemptRecord.State.ERROR)
        self.assertEqual(attempt.error_stage, "validation")

    @patch("django_http_inspector.replay.service.resolve_target")
    @patch("django_http_inspector.replay.service.send_request", side_effect=ReplayTransportError("timeout", "timed out"))
    def test_network_failure_is_persisted(self, _send, resolve):
        resolve.return_value = ReplayTarget("https://example.test/hook", "https", "example.test", 443, "/hook", ("93.184.216.34",), False)
        attempt = replay_exchange(self.source(), load_config(), self.repository)
        self.assertEqual(attempt.state, ReplayAttemptRecord.State.ERROR)
        self.assertEqual(attempt.error_stage, "timeout")
        self.assertEqual(attempt.error_summary, "timed out")

    @patch("django_http_inspector.replay.service.send_request")
    def test_attempt_commit_failure_does_not_send(self, send):
        class FailingRepository:
            def create_attempt(self, **kwargs):
                raise RuntimeError("commit failed")

        with self.assertRaisesMessage(RuntimeError, "commit failed"):
            replay_exchange(self.source(), load_config(), FailingRepository())
        send.assert_not_called()

    @patch("django_http_inspector.replay.service.resolve_target")
    @patch("django_http_inspector.replay.service.send_request")
    def test_final_update_failure_does_not_retry_transport(self, send, resolve):
        resolve.return_value = ReplayTarget(
            "https://example.test/hook", "https", "example.test", 443, "/hook", ("93.184.216.34",), False
        )
        send.return_value = (200, [], b"ok", 2, "93.184.216.34")
        original = self.repository.update_attempt
        self.repository.update_attempt = lambda attempt: (_ for _ in ()).throw(RuntimeError("disk full"))
        try:
            with self.assertLogs("django_http_inspector", level="ERROR"):
                attempt = replay_exchange(self.source(), load_config(), self.repository)
        finally:
            self.repository.update_attempt = original
        self.assertEqual(attempt.persistence_error, "disk full")
        send.assert_called_once()
