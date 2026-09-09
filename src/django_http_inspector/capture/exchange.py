import logging
import time

from django.utils import timezone

from django_http_inspector.storage.records import ExchangeRecord

logger = logging.getLogger("django_http_inspector")


class ExchangeCapture:
    def __init__(self, environ, input_stream, config, url_data, headers, repository):
        self.environ = environ
        self.input_stream = input_stream
        self.config = config
        self.started = time.monotonic()
        self.response_status = None
        self.response_headers = []
        self.response_body = bytearray()
        self.response_size = 0
        self.response_incomplete = False
        self.error_summary = ""
        self.finalized = False
        self.exchange = None
        self.repository = repository
        url, scheme, host, provenance = url_data
        if not repository.available:
            return
        nonce = next((value for name, value in headers if name.lower() == "x-django-http-inspector-replay"), None)
        try:
            self.exchange = repository.create_exchange(
                correlation_nonce=nonce,
                method=str(environ.get("REQUEST_METHOD", "GET")),
                url=url,
                url_provenance=provenance,
                scheme=scheme,
                host=host,
                path=str(environ.get("PATH_INFO", "/")),
                query_string=str(environ.get("QUERY_STRING", "")),
                request_headers=headers,
                request_content_type=str(environ.get("CONTENT_TYPE", "")),
                request_declared_size=input_stream.declared_size,
                client_addr=str(environ.get("REMOTE_ADDR", "")),
            )
        except Exception:
            logger.exception("Unable to create django-http-inspector exchange")

    def start(self, status, headers):
        self.response_status = int(str(status).split(" ", 1)[0])
        self.response_headers = [[str(name), str(value)] for name, value in headers]

    def observe_response(self, data):
        self.response_size += len(data)
        remaining = self.config.capture_max_bytes - len(self.response_body)
        if remaining > 0:
            self.response_body.extend(data[:remaining])

    def finalize(self, error=None, incomplete=False):
        if not self.exchange or self.finalized:
            return
        self.finalized = True
        now = timezone.now()
        if error:
            self.error_summary = f"{type(error).__name__}: {error}"[:2000]
        try:
            self.exchange.completed_at = now
            self.exchange.duration_ms = (time.monotonic() - self.started) * 1000
            self.exchange.request_body = bytes(self.input_stream.captured)
            self.exchange.request_observed_size = self.input_stream.observed_size
            self.exchange.request_captured_size = len(self.input_stream.captured)
            self.exchange.request_body_truncated = self.input_stream.truncated
            self.exchange.request_body_incomplete = self.input_stream.incomplete
            self.exchange.response_status = self.response_status
            self.exchange.response_headers = self.response_headers
            self.exchange.response_body = bytes(self.response_body)
            self.exchange.response_size = self.response_size
            self.exchange.response_body_truncated = self.response_size > self.config.capture_max_bytes
            self.exchange.response_body_incomplete = incomplete
            self.exchange.state = ExchangeRecord.State.APPLICATION_ERROR if error else ExchangeRecord.State.COMPLETE
            self.exchange.error_summary = self.error_summary
            self.repository.update_exchange(self.exchange)
            self.repository.prune(self.config.max_records)
        except Exception:
            logger.exception("Unable to finalize django-http-inspector exchange")
