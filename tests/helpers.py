import io


def environ(path="/echo/", method="GET", body=b"", host="localhost:8000", remote="127.0.0.1"):
    path_info, _, query = path.partition("?")
    return {
        "REQUEST_METHOD": method,
        "SCRIPT_NAME": "",
        "PATH_INFO": path_info,
        "QUERY_STRING": query,
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "8000",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "HTTP_HOST": host,
        "REMOTE_ADDR": remote,
        "CONTENT_LENGTH": str(len(body)) if body else "",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "http",
        "wsgi.input": io.BytesIO(body),
        "wsgi.errors": io.StringIO(),
        "wsgi.multithread": True,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
    }


def call_wsgi(app, env):
    result = {}

    def start_response(status, headers, exc_info=None):
        result["status"] = status
        result["headers"] = headers
        return lambda data: result.setdefault("written", []).append(data)

    iterable = app(env, start_response)
    try:
        result["body"] = b"".join(iterable)
    finally:
        close = getattr(iterable, "close", None)
        if close:
            close()
    return result
