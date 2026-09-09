from django.utils import timezone

from django_inspect.models import ReplayAttempt
from django_inspect.replay.target import TargetError, address_is_risky, resolve_target
from django_inspect.replay.transport import ReplayTransportError, send_request


def can_replay(exchange):
    return bool(
        exchange.url
        and not exchange.request_body_truncated
        and not exchange.request_body_incomplete
    )


def replay_exchange(exchange, config, allow_risky=False):
    attempt = ReplayAttempt.objects.create(
        source_exchange=exchange,
        method=exchange.method,
        url=exchange.url,
        request_headers=exchange.request_headers,
        request_body=bytes(exchange.request_body),
    )
    try:
        if not can_replay(exchange):
            raise TargetError("This request body was not captured completely.")
        target = resolve_target(exchange.url)
        attempt.target_addresses = list(target.addresses)
        attempt.save(update_fields=["target_addresses"])
        if target.risky and not allow_risky:
            raise TargetError("The replay target resolves to a non-public address and requires confirmation.")
        status, headers, body, size, peer = send_request(
            target,
            exchange.method,
            exchange.request_headers,
            bytes(exchange.request_body),
            config.replay_timeout,
            config.capture_max_bytes,
            str(attempt.correlation_nonce),
        )
        if address_is_risky(peer) and not target.risky:
            raise TargetError("The connected peer changed to a restricted address.")
        attempt.response_status = status
        attempt.response_headers = headers
        attempt.response_body = body
        attempt.response_size = size
        attempt.response_body_truncated = size > config.capture_max_bytes
        attempt.peer_address = peer
        attempt.state = ReplayAttempt.State.COMPLETE
    except TargetError as exc:
        attempt.state = ReplayAttempt.State.ERROR
        attempt.error_stage = "validation"
        attempt.error_summary = str(exc)
    except ReplayTransportError as exc:
        attempt.state = ReplayAttempt.State.ERROR
        attempt.error_stage = exc.stage
        attempt.error_summary = str(exc)
    attempt.completed_at = timezone.now()
    attempt.save()
    return attempt
