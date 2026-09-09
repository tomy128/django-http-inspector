from django.test import SimpleTestCase

from django_http_inspector.wrapper.response import CapturingIterable


class StubCapture:
    def __init__(self):
        self.body = b""
        self.finalizations = []

    def observe_response(self, data): self.body += data
    def finalize(self, error=None, incomplete=False): self.finalizations.append((error, incomplete))


class Closable:
    def __init__(self): self.closed = 0
    def __iter__(self): return iter([b"a", b"b"])
    def close(self): self.closed += 1


class ResponseCaptureTests(SimpleTestCase):
    def test_streams_and_closes_once(self):
        source = Closable()
        capture = StubCapture()
        wrapped = CapturingIterable(source, capture)
        self.assertEqual(list(wrapped), [b"a", b"b"])
        wrapped.close(); wrapped.close()
        self.assertEqual(source.closed, 1)
        self.assertEqual(capture.body, b"ab")
        self.assertEqual(len(capture.finalizations), 1)

    def test_early_close_is_incomplete(self):
        capture = StubCapture()
        wrapped = CapturingIterable(iter([b"a", b"b"]), capture)
        self.assertEqual(next(wrapped), b"a")
        wrapped.close()
        self.assertTrue(capture.finalizations[-1][1])
