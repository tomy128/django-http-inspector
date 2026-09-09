from types import SimpleNamespace

from django.test import SimpleTestCase

from django_http_inspector.replay.edit import EditValidationError, editable_body, encode_edited_body, parse_headers


class ReplayEditTests(SimpleTestCase):
    def exchange(self, body=b"hello", content_type="text/plain; charset=utf-8", **changes):
        values = {
            "request_body": body,
            "request_content_type": content_type,
            "request_body_truncated": False,
            "request_body_incomplete": False,
        }
        values.update(changes)
        return SimpleNamespace(**values)

    def test_raw_headers_preserve_duplicates_and_colons(self):
        self.assertEqual(
            parse_headers("X-Tag: one\nX-Tag: two\nAuthorization: Bearer a:b"),
            [["X-Tag", "one"], ["X-Tag", "two"], ["Authorization", "Bearer a:b"]],
        )

    def test_raw_headers_reject_invalid_name_control_and_unicode(self):
        for text in ("Bad Name: value", "X-Test: bad\x00value", "X-Test: snowman ☃"):
            with self.subTest(text=text), self.assertRaises(EditValidationError):
                parse_headers(text)

    def test_header_limits_are_enforced(self):
        with self.assertRaises(EditValidationError) as caught:
            parse_headers("\n".join(f"X-{number}: v" for number in range(201)))
        self.assertEqual(caught.exception.code, "headers_too_large")
        with self.assertRaises(EditValidationError) as caught:
            parse_headers("X-Test: " + "x" * (16 * 1024))
        self.assertEqual(caught.exception.code, "header_line_too_large")

    def test_text_body_uses_declared_charset(self):
        allowed, text, reason = editable_body(self.exchange("café".encode("latin-1"), "text/plain; charset=latin-1"))
        self.assertTrue(allowed)
        self.assertEqual(text, "café")
        self.assertEqual(reason, "")

    def test_binary_and_incomplete_bodies_are_not_editable(self):
        allowed, _, reason = editable_body(self.exchange(b"\x00\x01", "application/octet-stream"))
        self.assertFalse(allowed)
        self.assertIn("Binary", reason)
        allowed, _, reason = editable_body(self.exchange(request_body_incomplete=True))
        self.assertFalse(allowed)
        self.assertIn("not captured completely", reason)

    def test_empty_binary_body_is_editable_but_cannot_become_nonempty(self):
        self.assertTrue(editable_body(self.exchange(b"", "application/octet-stream"))[0])
        self.assertEqual(encode_edited_body([["Content-Type", "application/octet-stream"]], ""), b"")
        with self.assertRaises(EditValidationError) as caught:
            encode_edited_body([["Content-Type", "application/octet-stream"]], "payload")
        self.assertEqual(caught.exception.field, "body_text")

    def test_edited_content_type_controls_encoding(self):
        encoded = encode_edited_body([["Content-Type", "application/json; charset=utf-16"]], '{"ok": true}')
        self.assertEqual(encoded, '{"ok": true}'.encode("utf-16"))

    def test_repeated_content_type_is_rejected(self):
        with self.assertRaises(EditValidationError) as caught:
            encode_edited_body([["Content-Type", "text/plain"], ["content-type", "text/plain"]], "hello")
        self.assertEqual(caught.exception.field, "headers_text")
