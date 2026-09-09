import secrets

from django_http_inspector.config import load_config
from django_http_inspector.wrapper.input import CapturingInput
from django_http_inspector.wrapper.response import CapturingIterable


class InspectorWSGI:
    def __init__(self, application):
        self.application = application
        self.config = load_config()
        self.token = secrets.token_urlsafe(32)
        from django_http_inspector.inspector.app import InspectorApp

        self.inspector = InspectorApp(self.config, self.token)

    def __call__(self, environ, start_response):
        from django_http_inspector.capture.exchange import ExchangeCapture
        from django_http_inspector.capture.headers import request_headers_from_environ
        from django_http_inspector.capture.url import build_url

        path = str(environ.get("PATH_INFO", "/"))
        if not self.config.enabled:
            return self.application(environ, start_response)
        if self.config.is_inspector_path(path):
            return self.inspector(environ, start_response)
        if self.config.is_excluded_path(path):
            return self.application(environ, start_response)

        declared = 0
        try:
            if environ.get("CONTENT_LENGTH"):
                declared = int(environ["CONTENT_LENGTH"])
        except (TypeError, ValueError):
            declared = None
        wrapped_input = CapturingInput(environ["wsgi.input"], self.config.capture_max_bytes, declared)
        environ["wsgi.input"] = wrapped_input
        headers = request_headers_from_environ(environ)
        capture = ExchangeCapture(
            environ,
            wrapped_input,
            self.config,
            build_url(environ, self.config.trusted_proxy_cidrs),
            headers,
        )

        def capturing_start_response(status, response_headers, exc_info=None):
            capture.start(status, response_headers)
            write = start_response(status, response_headers, exc_info)

            def capturing_write(data):
                capture.observe_response(data)
                return write(data)

            return capturing_write

        try:
            iterable = self.application(environ, capturing_start_response)
        except Exception as exc:
            capture.finalize(error=exc, incomplete=True)
            raise
        return CapturingIterable(iterable, capture)
