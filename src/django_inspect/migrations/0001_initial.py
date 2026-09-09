import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Exchange",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("duration_ms", models.FloatField(blank=True, null=True)),
                ("method", models.CharField(max_length=32)),
                ("url", models.TextField(blank=True)),
                ("url_provenance", models.CharField(default="reconstructed", max_length=32)),
                ("scheme", models.CharField(blank=True, max_length=16)),
                ("host", models.TextField(blank=True)),
                ("path", models.TextField()),
                ("query_string", models.TextField(blank=True)),
                ("request_headers", models.JSONField(default=list)),
                ("request_body", models.BinaryField(default=bytes)),
                ("request_content_type", models.TextField(blank=True)),
                ("request_declared_size", models.BigIntegerField(blank=True, null=True)),
                ("request_observed_size", models.BigIntegerField(default=0)),
                ("request_captured_size", models.BigIntegerField(default=0)),
                ("request_body_truncated", models.BooleanField(default=False)),
                ("request_body_incomplete", models.BooleanField(default=False)),
                ("client_addr", models.TextField(blank=True)),
                ("response_status", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("response_headers", models.JSONField(default=list)),
                ("response_body", models.BinaryField(default=bytes)),
                ("response_size", models.BigIntegerField(default=0)),
                ("response_body_truncated", models.BooleanField(default=False)),
                ("response_body_incomplete", models.BooleanField(default=False)),
                ("state", models.CharField(choices=[("pending", "Pending"), ("complete", "Complete"), ("application_error", "Application error")], default="pending", max_length=32)),
                ("error_summary", models.TextField(blank=True)),
                ("correlation_diagnostic", models.CharField(blank=True, max_length=64)),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
        migrations.CreateModel(
            name="ReplayAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mode", models.CharField(choices=[("equivalent", "Equivalent")], default="equivalent", max_length=16)),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("state", models.CharField(choices=[("pending", "Pending"), ("complete", "Complete"), ("error", "Error")], default="pending", max_length=16)),
                ("method", models.CharField(max_length=32)),
                ("url", models.TextField()),
                ("request_headers", models.JSONField(default=list)),
                ("request_body", models.BinaryField(default=bytes)),
                ("response_status", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("response_headers", models.JSONField(default=list)),
                ("response_body", models.BinaryField(default=bytes)),
                ("response_size", models.BigIntegerField(default=0)),
                ("response_body_truncated", models.BooleanField(default=False)),
                ("error_stage", models.CharField(blank=True, max_length=32)),
                ("error_summary", models.TextField(blank=True)),
                ("correlation_nonce", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("correlation_claimed", models.BooleanField(default=False)),
                ("peer_address", models.CharField(blank=True, max_length=255)),
                ("target_addresses", models.JSONField(default=list)),
                ("source_exchange", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="replay_attempts", to="django_inspect.exchange")),
            ],
            options={"ordering": ("-submitted_at", "-id")},
        ),
        migrations.AddField(
            model_name="exchange",
            name="observed_replay_attempt",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="observed_exchange", to="django_inspect.replayattempt"),
        ),
    ]
