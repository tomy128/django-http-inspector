import secrets

from django.db import transaction

from django_inspect.models import ReplayAttempt


def claim_attempt(nonce):
    """Atomically claim a pending correlation nonce once."""
    with transaction.atomic():
        attempt = ReplayAttempt.objects.select_for_update().filter(
            correlation_nonce=nonce, correlation_claimed=False
        ).first()
        if attempt is None:
            return None
        if not secrets.compare_digest(str(attempt.correlation_nonce), str(nonce)):
            return None
        attempt.correlation_claimed = True
        attempt.save(update_fields=["correlation_claimed"])
        return attempt
