import json
import logging
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path

from django_http_inspector.storage.records import ExchangeRecord, ReplayAttemptRecord
from django_http_inspector.storage.schema import SCHEMA_V1, SCHEMA_VERSION

logger = logging.getLogger("django_http_inspector")


class StorageError(RuntimeError):
    pass


_initialization_lock = threading.Lock()


def _dump_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _dump_time(value):
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


EXCHANGE_JSON = {"request_headers", "response_headers"}
EXCHANGE_BOOL = {"request_body_truncated", "request_body_incomplete", "response_body_truncated", "response_body_incomplete"}
EXCHANGE_TIME = {"created_at", "completed_at"}
ATTEMPT_JSON = {"request_headers", "response_headers", "target_addresses"}
ATTEMPT_BOOL = {"response_body_truncated", "correlation_claimed"}
ATTEMPT_TIME = {"submitted_at", "completed_at"}


def _record(row, record_type, json_fields, bool_fields, time_fields):
    values = dict(row)
    for name in json_fields:
        values[name] = json.loads(values[name])
    for name in bool_fields:
        values[name] = bool(values[name])
    for name in time_fields:
        values[name] = _load_time(values[name])
    allowed = {item.name for item in fields(record_type) if item.name not in {"persistence_error", "network_attempted"}}
    return record_type(**{key: value for key, value in values.items() if key in allowed})


class InspectorRepository:
    available = True
    error = ""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(str(self.path), timeout=1.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=1000")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self):
        with _initialization_lock:
            connection = self._connect()
            try:
                mode = self._enable_wal(connection)
                if str(mode).lower() != "wal":
                    logger.warning("Inspector SQLite database does not support WAL; using %s journal mode", mode)
                connection.execute("BEGIN IMMEDIATE")
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version > SCHEMA_VERSION:
                    raise StorageError(f"Inspector database schema version {version} is newer than supported version {SCHEMA_VERSION}.")
                if version == 0:
                    tables = connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    ).fetchall()
                    if tables:
                        raise StorageError("Inspector database has tables but no supported schema version.")
                    for statement in SCHEMA_V1:
                        connection.execute(statement)
                    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                connection.execute("COMMIT")
                self.journal_mode = mode
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
            finally:
                connection.close()

    @staticmethod
    def _enable_wal(connection):
        deadline = time.monotonic() + 1.0
        while True:
            try:
                return connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower() or time.monotonic() >= deadline:
                    raise
                time.sleep(0.025)

    @contextmanager
    def _transaction(self, immediate=False):
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def _read(self, sql, parameters=()):
        connection = self._connect()
        try:
            return connection.execute(sql, parameters).fetchall()
        finally:
            connection.close()

    def create_exchange(self, correlation_nonce=None, **values):
        record = ExchangeRecord(**values)
        columns = [field.name for field in fields(ExchangeRecord) if field.name != "id"]
        encoded = self._encode(record, columns, EXCHANGE_JSON, EXCHANGE_BOOL, EXCHANGE_TIME)
        with self._transaction(immediate=bool(correlation_nonce)) as connection:
            cursor = connection.execute(
                f"INSERT INTO exchange_record ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                encoded,
            )
            record.id = cursor.lastrowid
            if correlation_nonce:
                claimed = connection.execute(
                    "UPDATE replay_attempt SET correlation_claimed=1 WHERE correlation_nonce=? AND state='pending' AND correlation_claimed=0",
                    (str(correlation_nonce),),
                )
                if claimed.rowcount:
                    attempt_id = connection.execute(
                        "SELECT id FROM replay_attempt WHERE correlation_nonce=?", (str(correlation_nonce),)
                    ).fetchone()[0]
                    connection.execute(
                        "UPDATE exchange_record SET observed_replay_attempt_id=? WHERE id=?", (attempt_id, record.id)
                    )
                    record.observed_replay_attempt_id = attempt_id
                elif connection.execute(
                    "SELECT 1 FROM replay_attempt WHERE correlation_nonce=? AND correlation_claimed=1", (str(correlation_nonce),)
                ).fetchone():
                    connection.execute(
                        "UPDATE exchange_record SET correlation_diagnostic='duplicate-correlation' WHERE id=?", (record.id,)
                    )
                    record.correlation_diagnostic = "duplicate-correlation"
        return record

    def update_exchange(self, record):
        columns = [field.name for field in fields(ExchangeRecord) if field.name != "id"]
        encoded = self._encode(record, columns, EXCHANGE_JSON, EXCHANGE_BOOL, EXCHANGE_TIME)
        with self._transaction() as connection:
            connection.execute(
                f"UPDATE exchange_record SET {','.join(name + '=?' for name in columns)} WHERE id=?",
                (*encoded, record.id),
            )

    def list_exchanges(self, limit=200):
        rows = self._read("SELECT * FROM exchange_record ORDER BY created_at DESC, id DESC LIMIT ?", (limit,))
        return [self._exchange(row) for row in rows]

    def get_exchange(self, exchange_id):
        rows = self._read("SELECT * FROM exchange_record WHERE id=?", (exchange_id,))
        return self._exchange(rows[0]) if rows else None

    def count_exchanges(self):
        return self._read("SELECT COUNT(*) AS count FROM exchange_record")[0]["count"]

    def prune(self, maximum):
        with self._transaction(immediate=True) as connection:
            connection.execute(
                "DELETE FROM exchange_record WHERE id IN (SELECT id FROM exchange_record ORDER BY created_at DESC, id DESC LIMIT -1 OFFSET ?)",
                (maximum,),
            )

    def clear(self):
        with self._transaction(immediate=True) as connection:
            connection.execute("DELETE FROM exchange_record")
            connection.execute("DELETE FROM replay_attempt")

    def delete_exchange(self, exchange_id):
        with self._transaction() as connection:
            connection.execute("DELETE FROM exchange_record WHERE id=?", (exchange_id,))

    def delete_attempt(self, attempt_id):
        with self._transaction() as connection:
            connection.execute("DELETE FROM replay_attempt WHERE id=?", (attempt_id,))

    def create_attempt(self, source_exchange_id, method, url, request_headers, request_body, mode="equivalent"):
        record = ReplayAttemptRecord(
            source_exchange_id=source_exchange_id,
            method=method,
            url=url,
            request_headers=request_headers,
            request_body=request_body,
            mode=mode,
            correlation_nonce=str(uuid.uuid4()),
        )
        columns = [field.name for field in fields(ReplayAttemptRecord) if field.name not in {"id", "persistence_error", "network_attempted"}]
        encoded = self._encode(record, columns, ATTEMPT_JSON, ATTEMPT_BOOL, ATTEMPT_TIME)
        with self._transaction() as connection:
            cursor = connection.execute(
                f"INSERT INTO replay_attempt ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", encoded
            )
            record.id = cursor.lastrowid
        return record

    def update_attempt(self, record):
        columns = [field.name for field in fields(ReplayAttemptRecord) if field.name not in {"id", "persistence_error", "network_attempted"}]
        encoded = self._encode(record, columns, ATTEMPT_JSON, ATTEMPT_BOOL, ATTEMPT_TIME)
        with self._transaction() as connection:
            connection.execute(
                f"UPDATE replay_attempt SET {','.join(name + '=?' for name in columns)} WHERE id=?", (*encoded, record.id)
            )

    def get_attempt(self, attempt_id):
        rows = self._read("SELECT * FROM replay_attempt WHERE id=?", (attempt_id,))
        return self._attempt(rows[0]) if rows else None

    def list_attempts(self, source_exchange_id, limit=20):
        rows = self._read(
            "SELECT * FROM replay_attempt WHERE source_exchange_id=? ORDER BY submitted_at DESC, id DESC LIMIT ?",
            (source_exchange_id, limit),
        )
        return [self._attempt(row) for row in rows]

    def count_attempts(self):
        return self._read("SELECT COUNT(*) AS count FROM replay_attempt")[0]["count"]

    @staticmethod
    def _encode(record, columns, json_fields, bool_fields, time_fields):
        result = []
        for name in columns:
            value = getattr(record, name)
            if name in json_fields:
                value = _dump_json(value)
            elif name in bool_fields:
                value = int(value)
            elif name in time_fields:
                value = _dump_time(value)
            result.append(value)
        return result

    @staticmethod
    def _exchange(row):
        return _record(row, ExchangeRecord, EXCHANGE_JSON, EXCHANGE_BOOL, EXCHANGE_TIME)

    @staticmethod
    def _attempt(row):
        return _record(row, ReplayAttemptRecord, ATTEMPT_JSON, ATTEMPT_BOOL, ATTEMPT_TIME)


class UnavailableRepository:
    available = False

    def __init__(self, error):
        self.error = str(error)
