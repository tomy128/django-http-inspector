from unittest.mock import patch

from django.test import SimpleTestCase

from django_http_inspector.inspector.presentation import parse_multipart, present_body


def multipart(parts, boundary="Boundary42", close=True, preamble=b""):
    chunks = [preamble]
    for headers, payload in parts:
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            "\r\n".join(headers).encode("latin-1"),
            b"\r\n\r\n",
            payload,
            b"\r\n",
        ])
    if close:
        chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks)


class BodyPresentationTests(SimpleTestCase):
    content_type = 'multipart/form-data; boundary="Boundary42"'

    def test_fields_keep_order_duplicates_empty_and_charset(self):
        body = multipart([
            (["Content-Disposition: form-data; name=tag"], b"one"),
            (["Content-Disposition: form-data; name=tag"], b"two"),
            (["Content-Disposition: form-data; name=empty"], b""),
            (["Content-Disposition: form-data; name=title", "Content-Type: text/plain; charset=latin-1"], "café".encode("latin-1")),
        ])
        text, kind, parts = present_body(body, self.content_type)
        self.assertEqual((text, kind), ("", "multipart"))
        self.assertEqual([(part["name"], part["value"]) for part in parts], [
            ("tag", "one"), ("tag", "two"), ("empty", ""), ("title", "café"),
        ])

    def test_binary_file_is_metadata_only_and_size_excludes_delimiter_crlf(self):
        secret = b"PK\x00\xffbinary"
        body = multipart([
            (["Content-Disposition: form-data; name=name"], b"AIConsole"),
            (["Content-Disposition: form-data; name=package; filename=file.zip", "Content-Type: application/zip"], secret),
        ])
        text, kind, parts = present_body(body, self.content_type)
        self.assertEqual((text, kind), ("", "multipart"))
        self.assertEqual(parts[1], {
            "kind": "file", "name": "package", "filename": "file.zip",
            "content_type": "application/zip", "size": len(secret),
        })
        self.assertNotIn(secret, repr(parts).encode())

    def test_empty_multipart_has_no_parts(self):
        self.assertEqual(present_body(b"--Boundary42--\r\n", self.content_type), ("", "multipart", []))

    def test_incomplete_body_and_malformed_structures_fall_back(self):
        valid = multipart([(["Content-Disposition: form-data; name=value"], b"hello")])
        self.assertEqual(present_body(valid, self.content_type, complete=False)[1:], ("raw", None))
        malformed = [
            multipart([(["Content-Disposition: form-data; name=value"], b"hello")], close=False),
            multipart([(["Content-Disposition: attachment; name=value"], b"hello")]),
            multipart([(["Content-Disposition: form-data"], b"hello")]),
            multipart([(["Content-Disposition: form-data; name=value", "Content-Transfer-Encoding: base64"], b"aGVsbG8=")]),
            multipart([(["Content-Disposition: form-data; name=value"], b"hello")], preamble=b"not-empty\r\n"),
        ]
        for body in malformed:
            with self.subTest(body=body[:60]):
                self.assertNotEqual(present_body(body, self.content_type)[1], "multipart")

    def test_nested_boundary_like_bytes_are_not_split(self):
        payload = b"before\r\n--Boundary42-not-a-delimiter\r\nafter"
        body = multipart([(["Content-Disposition: form-data; name=file; filename=a.bin"], payload)])
        parts = parse_multipart(body, self.content_type)
        self.assertEqual(parts[0]["size"], len(payload))

    def test_crlf_in_content_type_and_repeated_parameters_fall_back(self):
        body = multipart([(["Content-Disposition: form-data; name=value"], b"hello")])
        invalid_types = [
            "multipart/form-data; boundary=Boundary42\r\nX-Evil: yes",
            "multipart/form-data; boundary=Boundary42; boundary=other",
        ]
        for content_type in invalid_types:
            self.assertNotEqual(present_body(body, content_type)[1], "multipart")
        duplicate_name = multipart([(["Content-Disposition: form-data; name=one; name=two"], b"hello")])
        self.assertNotEqual(present_body(duplicate_name, self.content_type)[1], "multipart")

    def test_resource_limits_fall_back(self):
        body = multipart([(["Content-Disposition: form-data; name=value"], b"hello")])
        with patch("django_http_inspector.inspector.presentation.MULTIPART_PREVIEW_BYTES", len(body) - 1):
            self.assertNotEqual(present_body(body, self.content_type)[1], "multipart")
        with patch("django_http_inspector.inspector.presentation.MAX_MULTIPART_PARTS", 0):
            self.assertNotEqual(present_body(body, self.content_type)[1], "multipart")
        with patch("django_http_inspector.inspector.presentation.MAX_MULTIPART_FIELD", 4):
            self.assertNotEqual(present_body(body, self.content_type)[1], "multipart")

    def test_existing_json_form_raw_and_binary_contract(self):
        self.assertEqual(present_body(b'{"ok":true}', "application/json"), ('{\n  "ok": true\n}', "json", None))
        self.assertEqual(present_body(b"a=1&a=2", "application/x-www-form-urlencoded")[1:], ("form", None))
        self.assertEqual(present_body(b"hello", "text/plain"), ("hello", "raw", None))
        self.assertEqual(present_body(b"\xff", "application/octet-stream")[1:], ("binary", None))
