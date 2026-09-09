import logging

from django_http_inspector.replay.target import TargetError, address_is_risky, resolve_target
from django_http_inspector.replay.transport import ReplayTransportError, send_request
from django_http_inspector.storage.records import ReplayAttemptRecord, utc_now

logger = logging.getLogger("django_http_inspector")


def can_replay(exchange):
    return bool(
        exchange.url
        and not exchange.request_body_truncated
        and not exchange.request_body_incomplete
    )


def replay_exchange(exchange, config, repository, allow_risky=False, headers=None, body=None, mode="equivalent"):
    request_headers = exchange.request_headers if headers is None else headers
    request_body = bytes(exchange.request_body) if body is None else body
    attempt = repository.create_attempt(
        source_exchange_id=exchange.id,
        method=exchange.method,
        url=exchange.url,
        request_headers=request_headers,
        request_body=request_body,
        mode=mode,
    )
    try:
        if not can_replay(exchange):
            raise TargetError("This request body was not captured completely.")
        target = resolve_target(exchange.url)
        attempt.target_addresses = list(target.addresses)
        if target.risky and not allow_risky:
            raise TargetError("The replay target resolves to a non-public address and requires confirmation.")
        attempt.network_attempted = True
        status, response_headers, response_body, size, peer = send_request(
            target,
            exchange.method,
            request_headers,
            request_body,
            config.replay_timeout,
            config.capture_max_bytes,
            str(attempt.correlation_nonce),
        )
        if address_is_risky(peer) and not target.risky:
            raise TargetError("The connected peer changed to a restricted address.")
        attempt.response_status = status
        attempt.response_headers = response_headers
        attempt.response_body = response_body
        attempt.response_size = size
        attempt.response_body_truncated = size > config.capture_max_bytes
        attempt.peer_address = peer
        attempt.state = ReplayAttemptRecord.State.COMPLETE
    except TargetError as exc:
        attempt.state = ReplayAttemptRecord.State.ERROR
        attempt.error_stage = "validation"
        attempt.error_summary = str(exc)
    except ReplayTransportError as exc:
        attempt.state = ReplayAttemptRecord.State.ERROR
        attempt.error_stage = exc.stage
        attempt.error_summary = str(exc)
    attempt.completed_at = utc_now()
    try:
        repository.update_attempt(attempt)
    except Exception as exc:
        logger.exception("Replay was sent or evaluated, but its final result could not be saved")
        attempt.persistence_error = str(exc)
    return attempt
