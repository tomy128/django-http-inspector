import threading
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

from django.core.wsgi import get_wsgi_application
from django.test import TransactionTestCase

from django_inspect import InspectorWSGI
from django_inspect.models import Exchange, ReplayAttempt
from django_inspect.replay.service import replay_exchange
from django_inspect.replay.correlation import claim_attempt


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class EndToEndReplayTests(TransactionTestCase):
    reset_sequences = True

    def test_replay_uses_http_and_correlates_inbound_exchange(self):
        app = InspectorWSGI(get_wsgi_application())
        server = make_server("127.0.0.1", 0, app, server_class=ThreadingWSGIServer)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/echo/?source=replay"
            source = Exchange.objects.create(
                method="POST",
                path="/echo/",
                query_string="source=replay",
                url=url,
                request_headers=[["Content-Type", "text/plain"]],
                request_body=b"from-replay",
                request_declared_size=11,
                request_observed_size=11,
                request_captured_size=11,
                state=Exchange.State.COMPLETE,
            )
            attempt = replay_exchange(source, app.config, allow_risky=True)
            attempt.refresh_from_db()
            self.assertEqual(attempt.state, ReplayAttempt.State.COMPLETE)
            self.assertEqual(attempt.response_status, 200)
            self.assertEqual(attempt.peer_address, "127.0.0.1")
            inbound = Exchange.objects.exclude(pk=source.pk).get()
            self.assertEqual(inbound.observed_replay_attempt_id, attempt.id)
            self.assertEqual(bytes(inbound.request_body), b"from-replay")
            self.assertEqual(inbound.query_string, "source=replay")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_correlation_nonce_can_only_be_claimed_once(self):
        attempt = ReplayAttempt.objects.create(method="GET", url="http://example.test/")
        self.assertEqual(claim_attempt(str(attempt.correlation_nonce)).id, attempt.id)
        self.assertIsNone(claim_attempt(str(attempt.correlation_nonce)))
