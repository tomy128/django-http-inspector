import json
from email import policy
from email.message import Message
from email.parser import BytesParser
from urllib.parse import parse_qsl


MULTIPART_PREVIEW_BYTES = 1024 * 1024
MAX_MULTIPART_PARTS = 200
MAX_MULTIPART_METADATA = 1024
MAX_MULTIPART_FIELD = 256 * 1024
MAX_MULTIPART_TEXT = 512 * 1024
IDENTITY_ENCODINGS = {"", "7bit", "8bit", "binary"}


class MultipartPreviewError(ValueError):
    pass


def decode_body(body):
    try:
        return bytes(body).decode("utf-8")
    except UnicodeDecodeError:
        return "Binary body — preview unavailable"


def _fallback(body, content_type):
    raw = decode_body(body)
    lowered = (content_type or "").lower()
    if "json" in lowered:
        try:
            return json.dumps(json.loads(raw), indent=2, ensure_ascii=False), "json", None
        except (ValueError, TypeError):
            pass
    if "application/x-www-form-urlencoded" in lowered:
        try:
            return json.dumps(parse_qsl(raw, keep_blank_values=True), indent=2, ensure_ascii=False), "form", None
        except ValueError:
            pass
    return raw, "binary" if raw == "Binary body — preview unavailable" else "raw", None


def _contains_control(value):
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _raw_parameter_names(value):
    segments = []
    current = []
    quoted = escaped = False
    for character in value:
        if escaped:
            escaped = False
        elif quoted and character == "\\":
            escaped = True
        elif character == '"':
            quoted = not quoted
        elif character == ";" and not quoted:
            segments.append("".join(current))
            current = []
            continue
        current.append(character)
    if quoted or escaped:
        raise MultipartPreviewError
    segments.append("".join(current))
    return [segment.split("=", 1)[0].strip().lower() for segment in segments[1:] if "=" in segment]


def _multipart_boundary(content_type):
    if not isinstance(content_type, str) or "\r" in content_type or "\n" in content_type:
        raise MultipartPreviewError
    if _raw_parameter_names(content_type).count("boundary") != 1:
        raise MultipartPreviewError
    header = Message()
    header["Content-Type"] = content_type
    if header.get_content_type().lower() != "multipart/form-data":
        raise MultipartPreviewError
    params = header.get_params(header="Content-Type", failobj=[])[1:]
    boundaries = [value for name, value in params if name.lower() == "boundary"]
    if len(boundaries) != 1 or not isinstance(boundaries[0], str) or not boundaries[0]:
        raise MultipartPreviewError
    try:
        encoded = boundaries[0].encode("ascii")
    except UnicodeEncodeError as exc:
        raise MultipartPreviewError from exc
    if len(encoded) > 70:
        raise MultipartPreviewError
    return encoded


def _validate_framing(body, boundary):
    marker = b"--" + boundary
    closing = marker + b"--"
    if body in {closing, closing + b"\r\n"}:
        return True
    if not body.startswith(marker + b"\r\n"):
        raise MultipartPreviewError
    closing_delimiter = b"\r\n" + closing
    if body.count(closing_delimiter) != 1:
        raise MultipartPreviewError
    if not (body.endswith(closing_delimiter) or body.endswith(closing_delimiter + b"\r\n")):
        raise MultipartPreviewError
    return False


def _parameter_values(part, key):
    params = part.get_params(header="Content-Disposition", failobj=[])[1:]
    return [value for name, value in params if name.lower() == key]


def _raw_header(part, name):
    values = [value for header_name, value in part.raw_items() if header_name.lower() == name.lower()]
    if len(values) != 1:
        raise MultipartPreviewError
    return values[0]


def parse_multipart(body, content_type):
    body = bytes(body)
    if len(body) > MULTIPART_PREVIEW_BYTES:
        raise MultipartPreviewError
    boundary = _multipart_boundary(content_type)
    if _validate_framing(body, boundary):
        return []
    try:
        content_type_bytes = content_type.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise MultipartPreviewError from exc
    message = BytesParser(policy=policy.default).parsebytes(
        b"MIME-Version: 1.0\r\nContent-Type: " + content_type_bytes + b"\r\n\r\n" + body
    )
    if message.defects or not message.is_multipart():
        raise MultipartPreviewError
    if (message.preamble or "").strip() or (message.epilogue or "").strip():
        raise MultipartPreviewError
    parts = list(message.iter_parts())
    if len(parts) > MAX_MULTIPART_PARTS:
        raise MultipartPreviewError
    result = []
    text_total = 0
    for part in parts:
        if part.defects or part.is_multipart() or part.get_content_disposition() != "form-data":
            raise MultipartPreviewError
        disposition = _raw_header(part, "Content-Disposition")
        parameter_names = _raw_parameter_names(disposition)
        if parameter_names.count("name") != 1 or sum(
            name == "filename" or name.startswith("filename*") for name in parameter_names
        ) > 1:
            raise MultipartPreviewError
        names = _parameter_values(part, "name")
        filenames = _parameter_values(part, "filename")
        if len(names) != 1 or len(filenames) > 1:
            raise MultipartPreviewError
        name = names[0]
        filename_present = len(filenames) == 1
        filename = filenames[0] if filename_present else ""
        content_type_value = part.get_content_type() if part.get("Content-Type") else "application/octet-stream"
        metadata = [name, content_type_value]
        if filename_present:
            metadata.append(filename)
        if any(not isinstance(value, str) or len(value) > MAX_MULTIPART_METADATA or _contains_control(value) for value in metadata):
            raise MultipartPreviewError
        transfer_encoding = str(part.get("Content-Transfer-Encoding", "")).strip().lower()
        if transfer_encoding not in IDENTITY_ENCODINGS:
            raise MultipartPreviewError
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            raise MultipartPreviewError
        if filename_present:
            result.append({
                "kind": "file", "name": name, "filename": filename,
                "content_type": content_type_value, "size": len(payload),
            })
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            value = payload.decode(charset, "strict")
        except (LookupError, UnicodeDecodeError) as exc:
            raise MultipartPreviewError from exc
        if len(value) > MAX_MULTIPART_FIELD or _contains_control(value.replace("\r", "").replace("\n", "")):
            raise MultipartPreviewError
        text_total += len(value)
        if text_total > MAX_MULTIPART_TEXT:
            raise MultipartPreviewError
        result.append({"kind": "field", "name": name, "value": value})
    return result


def present_body(body, content_type, *, complete=True):
    if complete and str(content_type or "").split(";", 1)[0].strip().lower() == "multipart/form-data":
        try:
            return "", "multipart", parse_multipart(body, content_type)
        except (MultipartPreviewError, ValueError, TypeError):
            pass
    return _fallback(body, content_type)
