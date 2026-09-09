import json
from urllib.parse import parse_qsl


def decode_body(body):
    try:
        return bytes(body).decode("utf-8")
    except UnicodeDecodeError:
        return "Binary body — preview unavailable"


def present_body(body, content_type):
    raw = decode_body(body)
    if "json" in (content_type or "").lower():
        try:
            return json.dumps(json.loads(raw), indent=2, ensure_ascii=False), "json"
        except (ValueError, TypeError):
            pass
    if "application/x-www-form-urlencoded" in (content_type or "").lower():
        try:
            return json.dumps(parse_qsl(raw, keep_blank_values=True), indent=2, ensure_ascii=False), "form"
        except ValueError:
            pass
    return raw, "raw"
