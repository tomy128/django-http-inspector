import uuid

from django.db import models


class Exchange(models.Model):
    class State(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETE = "complete", "Complete"
        APPLICATION_ERROR = "application_error", "Application error"

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.FloatField(null=True, blank=True)
    method = models.CharField(max_length=32)
    url = models.TextField(blank=True)
    url_provenance = models.CharField(max_length=32, default="reconstructed")
    scheme = models.CharField(max_length=16, blank=True)
    host = models.TextField(blank=True)
    path = models.TextField()
    query_string = models.TextField(blank=True)
    request_headers = models.JSONField(default=list)
    request_body = models.BinaryField(default=bytes)
    request_content_type = models.TextField(blank=True)
    request_declared_size = models.BigIntegerField(null=True, blank=True)
    request_observed_size = models.BigIntegerField(default=0)
    request_captured_size = models.BigIntegerField(default=0)
    request_body_truncated = models.BooleanField(default=False)
    request_body_incomplete = models.BooleanField(default=False)
    client_addr = models.TextField(blank=True)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_headers = models.JSONField(default=list)
    response_body = models.BinaryField(default=bytes)
    response_size = models.BigIntegerField(default=0)
    response_body_truncated = models.BooleanField(default=False)
    response_body_incomplete = models.BooleanField(default=False)
    state = models.CharField(max_length=32, choices=State.choices, default=State.PENDING)
    error_summary = models.TextField(blank=True)
    correlation_diagnostic = models.CharField(max_length=64, blank=True)
    observed_replay_attempt = models.OneToOneField(
        "ReplayAttempt", null=True, blank=True, related_name="observed_exchange", on_delete=models.SET_NULL
    )

    class Meta:
        ordering = ("-created_at", "-id")


class ReplayAttempt(models.Model):
    class Mode(models.TextChoices):
        EQUIVALENT = "equivalent", "Equivalent"

    class State(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETE = "complete", "Complete"
        ERROR = "error", "Error"

    source_exchange = models.ForeignKey(Exchange, null=True, blank=True, related_name="replay_attempts", on_delete=models.SET_NULL)
    mode = models.CharField(max_length=16, choices=Mode.choices, default=Mode.EQUIVALENT)
    submitted_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    state = models.CharField(max_length=16, choices=State.choices, default=State.PENDING)
    method = models.CharField(max_length=32)
    url = models.TextField()
    request_headers = models.JSONField(default=list)
    request_body = models.BinaryField(default=bytes)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_headers = models.JSONField(default=list)
    response_body = models.BinaryField(default=bytes)
    response_size = models.BigIntegerField(default=0)
    response_body_truncated = models.BooleanField(default=False)
    error_stage = models.CharField(max_length=32, blank=True)
    error_summary = models.TextField(blank=True)
    correlation_nonce = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    correlation_claimed = models.BooleanField(default=False)
    peer_address = models.CharField(max_length=255, blank=True)
    target_addresses = models.JSONField(default=list)

    class Meta:
        ordering = ("-submitted_at", "-id")
