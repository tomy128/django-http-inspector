import io

from django.test import SimpleTestCase

from django_inspect.wrapper.input import CapturingInput


class InputCaptureTests(SimpleTestCase):
    def test_tees_without_pre_reading_and_truncates_capture(self):
        source = io.BytesIO(b"0123456789")
        wrapped = CapturingInput(source, 4, 10)
        self.assertEqual(source.tell(), 0)
        self.assertEqual(wrapped.read(3), b"012")
        self.assertEqual(wrapped.readline(), b"3456789")
        self.assertEqual(bytes(wrapped.captured), b"0123")
        self.assertEqual(wrapped.observed_size, 10)
        self.assertTrue(wrapped.truncated)
        self.assertFalse(wrapped.incomplete)

    def test_partial_read_is_incomplete(self):
        wrapped = CapturingInput(io.BytesIO(b"abcdef"), 20, 6)
        self.assertEqual(wrapped.read(2), b"ab")
        self.assertTrue(wrapped.incomplete)

    def test_iteration(self):
        wrapped = CapturingInput(io.BytesIO(b"one\ntwo\n"), 20, 8)
        self.assertEqual(list(wrapped), [b"one\n", b"two\n"])
        self.assertFalse(wrapped.incomplete)

    def test_large_stream_capture_stays_bounded(self):
        chunk = b"x" * (1024 * 1024)

        class RepeatingStream:
            remaining = 100

            def read(self, size=-1):
                if not self.remaining:
                    return b""
                self.remaining -= 1
                return chunk

        wrapped = CapturingInput(RepeatingStream(), 1024, 100 * 1024 * 1024)
        while wrapped.read(1024 * 1024):
            pass
        self.assertEqual(wrapped.observed_size, 100 * 1024 * 1024)
        self.assertEqual(len(wrapped.captured), 1024)
        self.assertTrue(wrapped.truncated)
