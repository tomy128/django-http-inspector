HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def request_headers_from_environ(environ):
    headers = []
    if environ.get("CONTENT_TYPE"):
        headers.append(["Content-Type", str(environ["CONTENT_TYPE"])])
    if environ.get("CONTENT_LENGTH"):
        headers.append(["Content-Length", str(environ["CONTENT_LENGTH"])])
    for key, value in environ.items():
        if key.startswith("HTTP_"):
            name = "-".join(part.title() for part in key[5:].split("_"))
            headers.append([name, str(value)])
    return headers


def replay_headers(headers):
    result = []
    for name, value in headers:
        lower = name.lower()
        if lower in HOP_BY_HOP_HEADERS or lower in {"content-length", "host", "x-django-inspect-replay"}:
            continue
        result.append((name, value))
    return result
