import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from django.test import SimpleTestCase

from django_inspect.replay.target import resolve_target
from django_inspect.replay.transport import send_request


class Handler(BaseHTTPRequestHandler):
    seen = None

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        type(self).seen = (self.path, self.headers.get("Host"), self.headers.get("X-Django-Inspect-Replay"), body)
        self.send_response(201)
        self.send_header("X-Test", "yes")
        self.end_headers()
        self.wfile.write(b"accepted")

    def log_message(self, *args):
        pass


class ReplayTransportTests(SimpleTestCase):
    def test_sends_real_http_request_to_captured_target(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/hook?a=x%2Fy"
            target = resolve_target(url)
            status, headers, body, size, peer = send_request(
                target, "POST", [["Content-Type", "text/plain"], ["Connection", "keep-alive"]], b"payload", 2, 100, "nonce"
            )
            self.assertEqual(status, 201)
            self.assertEqual(body, b"accepted")
            self.assertEqual(size, 8)
            self.assertEqual(peer, "127.0.0.1")
            self.assertEqual(Handler.seen[0], "/hook?a=x%2Fy")
            self.assertEqual(Handler.seen[2:], ("nonce", b"payload"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
