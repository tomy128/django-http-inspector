import threading
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

from django.core.wsgi import get_wsgi_application
from django.test import SimpleTestCase

from django_http_inspector import InspectorWSGI
from django_http_inspector.replay.service import replay_exchange
from django_http_inspector.storage.records import ReplayAttemptRecord
from tests.helpers import IsolatedStorageMixin


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class EndToEndReplayTests(IsolatedStorageMixin, SimpleTestCase):

    def test_replay_uses_http_and_correlates_inbound_exchange(self):
        app = InspectorWSGI(get_wsgi_application())
        server = make_server("127.0.0.1", 0, app, server_class=ThreadingWSGIServer)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/echo/?source=replay"
            source = app.repository.create_exchange(
                method="POST",
                path="/echo/",
                query_string="source=replay",
                url=url,
                request_headers=[["Content-Type", "text/plain"]],
                request_body=b"from-replay",
                request_declared_size=11,
                request_observed_size=11,
                request_captured_size=11,
                state="complete",
            )
            attempt = replay_exchange(source, app.config, app.repository, allow_risky=True)
            attempt = app.repository.get_attempt(attempt.id)
            self.assertEqual(attempt.state, ReplayAttemptRecord.State.COMPLETE)
            self.assertEqual(attempt.response_status, 200)
            self.assertEqual(attempt.peer_address, "127.0.0.1")
            inbound = next(exchange for exchange in app.repository.list_exchanges() if exchange.id != source.id)
            self.assertEqual(inbound.observed_replay_attempt_id, attempt.id)
            self.assertEqual(bytes(inbound.request_body), b"from-replay")
            self.assertEqual(inbound.query_string, "source=replay")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_correlation_nonce_can_only_be_claimed_once(self):
        app = InspectorWSGI(get_wsgi_application())
        attempt = app.repository.create_attempt(None, "GET", "http://example.test/", [], b"")
        first = app.repository.create_exchange(method="GET", path="/one", correlation_nonce=attempt.correlation_nonce)
        second = app.repository.create_exchange(method="GET", path="/two", correlation_nonce=attempt.correlation_nonce)
        self.assertEqual(first.observed_replay_attempt_id, attempt.id)
        self.assertIsNone(second.observed_replay_attempt_id)
        self.assertEqual(second.correlation_diagnostic, "duplicate-correlation")
