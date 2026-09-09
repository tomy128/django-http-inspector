import re
from email.message import Message


TOKEN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
MEDIA_TYPE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+/[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
TEXT_APPLICATION_TYPES = {"application/json", "application/xml", "application/x-www-form-urlencoded"}
MAX_HEADER_LINES = 200
MAX_HEADER_LINE_BYTES = 16 * 1024
MAX_HEADERS_BYTES = 256 * 1024


class EditValidationError(ValueError):
    def __init__(self, code, message, field, line=None, status=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.line = line
        self.status = status


def headers_to_text(headers):
    return "\n".join(f"{name}: {value}" for name, value in headers)


def parse_headers(text):
    if "\r" in text:
        raise EditValidationError("invalid_header", "Carriage returns are not allowed in headers.", "headers_text")
    parsed = []
    total = 0
    lines = text.split("\n")
    nonempty = [(number, line) for number, line in enumerate(lines, 1) if line]
    if len(nonempty) > MAX_HEADER_LINES:
        raise EditValidationError("headers_too_large", f"Headers may contain at most {MAX_HEADER_LINES} lines.", "headers_text")
    for number, line in nonempty:
        if ":" not in line:
            raise EditValidationError("invalid_header", f"Header on line {number} must contain ':'.", "headers_text", number)
        name, value = line.split(":", 1)
        name = name.strip()
        if not TOKEN.fullmatch(name):
            raise EditValidationError("invalid_header", f"Header name is invalid on line {number}.", "headers_text", number)
        if value.startswith(" "):
            value = value[1:]
        if any(ord(character) < 32 and character != "\t" or ord(character) == 127 for character in value):
            raise EditValidationError("invalid_header", f"Header value contains a control character on line {number}.", "headers_text", number)
        try:
            encoded = f"{name}:{value}".encode("latin-1")
        except UnicodeEncodeError:
            raise EditValidationError("invalid_header", f"Header value is not ISO-8859-1 encodable on line {number}.", "headers_text", number)
        if len(encoded) > MAX_HEADER_LINE_BYTES:
            raise EditValidationError("header_line_too_large", f"Header on line {number} exceeds 16 KiB.", "headers_text", number)
        total += len(encoded)
        if total > MAX_HEADERS_BYTES:
            raise EditValidationError("headers_too_large", "Headers exceed 256 KiB.", "headers_text")
        parsed.append([name, value])
    return parsed


def _content_type(value, field="body_text"):
    if not value:
        return "", "utf-8"
    if "\r" in value or "\n" in value:
        raise EditValidationError("invalid_content_type", "Content-Type is malformed.", field)
    media_type = value.split(";", 1)[0].strip().lower()
    if not MEDIA_TYPE.fullmatch(media_type):
        raise EditValidationError("invalid_content_type", "Content-Type is malformed.", field)
    message = Message()
    message["content-type"] = value
    charsets = [item[1] for item in message.get_params(header="content-type", failobj=[])[1:] if item[0].lower() == "charset"]
    if len(charsets) > 1 or (charsets and not charsets[0]):
        raise EditValidationError("invalid_content_type", "Content-Type has an invalid or repeated charset.", field)
    charset = charsets[0] if charsets else "utf-8"
    try:
        "".encode(charset)
    except LookupError:
        raise EditValidationError("unknown_charset", f"Unknown body charset: {charset}.", field)
    return media_type, charset


def _is_textual(media_type):
    return (
        not media_type
        or media_type.startswith("text/")
        or media_type in TEXT_APPLICATION_TYPES
        or media_type.endswith("+json")
        or media_type.endswith("+xml")
    )


def editable_body(exchange):
    if exchange.request_body_truncated or exchange.request_body_incomplete:
        return False, "", "The request body was not captured completely."
    body = bytes(exchange.request_body)
    if not body:
        return True, "", ""
    try:
        media_type, charset = _content_type(exchange.request_content_type)
    except EditValidationError as exc:
        return False, "", exc.message
    if not _is_textual(media_type):
        return False, "", "Binary request bodies cannot be edited."
    try:
        return True, body.decode(charset, "strict"), ""
    except UnicodeDecodeError:
        return False, "", f"The request body is not valid {charset} text."


def encode_edited_body(headers, body_text):
    content_types = [value for name, value in headers if name.lower() == "content-type"]
    if len(content_types) > 1:
        raise EditValidationError("invalid_content_type", "Only one Content-Type header is allowed.", "headers_text")
    media_type, charset = _content_type(content_types[0] if content_types else "")
    if body_text and not _is_textual(media_type):
        raise EditValidationError("body_content_type", "A non-empty edited body requires a textual Content-Type.", "body_text")
    try:
        return body_text.encode(charset, "strict")
    except UnicodeEncodeError:
        raise EditValidationError("body_encoding", f"The edited body cannot be encoded as {charset}.", "body_text")
