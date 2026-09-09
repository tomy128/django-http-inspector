import sqlite3
import subprocess
import sys
import time

from django.test import SimpleTestCase

from django_http_inspector.storage import InspectorRepository
from tests.helpers import IsolatedStorageMixin


class StorageTests(IsolatedStorageMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.repository = InspectorRepository(self.storage_path)

    def test_attempt_survives_source_deletion(self):
        exchange = self.repository.create_exchange(method="GET", path="/", url="http://example.test/")
        attempt = self.repository.create_attempt(exchange.id, "GET", exchange.url, [], b"")
        self.repository.prune(0)
        self.assertIsNone(self.repository.get_attempt(attempt.id).source_exchange_id)

    def test_prune_keeps_latest(self):
        for index in range(4):
            self.repository.create_exchange(method="GET", path=f"/{index}")
        self.repository.prune(2)
        self.assertEqual(self.repository.count_exchanges(), 2)

    def test_reopening_repository_preserves_records(self):
        self.repository.create_exchange(method="GET", path="/persistent")
        reopened = InspectorRepository(self.storage_path)
        self.assertEqual(reopened.list_exchanges()[0].path, "/persistent")

    def test_repository_creates_custom_parent_directory(self):
        nested = self.storage_path.parent / "runtime" / "nested" / "inspect.sqlite3"
        InspectorRepository(nested)
        self.assertTrue(nested.exists())

    def test_clear_removes_exchanges_and_attempts(self):
        exchange = self.repository.create_exchange(method="GET", path="/")
        self.repository.create_attempt(exchange.id, "GET", "http://example.test/", [], b"")
        self.repository.clear()
        self.assertEqual(self.repository.count_exchanges(), 0)
        self.assertEqual(self.repository.count_attempts(), 0)

    def test_deleting_attempt_nulls_observed_link(self):
        attempt = self.repository.create_attempt(None, "GET", "http://example.test/", [], b"")
        exchange = self.repository.create_exchange(
            method="GET", path="/", correlation_nonce=attempt.correlation_nonce
        )
        self.repository.delete_attempt(attempt.id)
        self.assertIsNone(self.repository.get_exchange(exchange.id).observed_replay_attempt_id)

    def test_failed_correlation_link_rolls_back_claim_and_exchange(self):
        attempt = self.repository.create_attempt(None, "GET", "http://example.test/", [], b"")
        with self.repository._transaction() as connection:
            connection.execute(
                """CREATE TRIGGER reject_observed BEFORE UPDATE OF observed_replay_attempt_id ON exchange_record
                WHEN NEW.observed_replay_attempt_id IS NOT NULL BEGIN SELECT RAISE(ABORT, 'reject'); END"""
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.repository.create_exchange(method="GET", path="/", correlation_nonce=attempt.correlation_nonce)
        self.assertFalse(self.repository.get_attempt(attempt.id).correlation_claimed)
        self.assertEqual(self.repository.count_exchanges(), 0)

    def test_newer_schema_is_rejected(self):
        self.storage_path.unlink()
        connection = sqlite3.connect(self.storage_path)
        connection.execute("PRAGMA user_version=99")
        connection.close()
        with self.assertRaisesMessage(Exception, "newer than supported"):
            InspectorRepository(self.storage_path)

    def test_two_processes_can_initialize_same_database(self):
        self.storage_path.unlink()
        script = "from django_http_inspector.storage import InspectorRepository; InspectorRepository(%r)" % str(self.storage_path)
        processes = [
            subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for _ in range(2)
        ]
        results = [process.communicate(timeout=10) for process in processes]
        self.assertEqual([process.returncode for process in processes], [0, 0], results)
        self.assertEqual(sqlite3.connect(self.storage_path).execute("PRAGMA user_version").fetchone()[0], 1)

    def test_write_lock_wait_is_bounded(self):
        blocker = sqlite3.connect(self.storage_path, isolation_level=None)
        blocker.execute("BEGIN IMMEDIATE")
        started = time.monotonic()
        try:
            with self.assertRaises(sqlite3.OperationalError):
                self.repository.create_exchange(method="GET", path="/locked")
        finally:
            blocker.execute("ROLLBACK")
            blocker.close()
        self.assertLess(time.monotonic() - started, 2.5)
