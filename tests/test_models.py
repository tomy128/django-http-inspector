from django.test import TestCase

from django_inspect.capture.exchange import ExchangeCapture
from django_inspect.models import Exchange, ReplayAttempt


class ModelTests(TestCase):
    def test_attempt_survives_source_deletion(self):
        exchange = Exchange.objects.create(method="GET", path="/", url="http://example.test/")
        attempt = ReplayAttempt.objects.create(source_exchange=exchange, method="GET", url=exchange.url)
        exchange.delete()
        attempt.refresh_from_db()
        self.assertIsNone(attempt.source_exchange)

    def test_prune_keeps_latest(self):
        for index in range(4):
            Exchange.objects.create(method="GET", path=f"/{index}")
        ExchangeCapture.prune(2)
        self.assertEqual(Exchange.objects.count(), 2)
