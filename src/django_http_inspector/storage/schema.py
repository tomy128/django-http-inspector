SCHEMA_VERSION = 1

SCHEMA_V1 = (
    """CREATE TABLE replay_attempt (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_exchange_id INTEGER NULL REFERENCES exchange_record(id) ON DELETE SET NULL,
        mode TEXT NOT NULL DEFAULT 'equivalent', submitted_at TEXT NOT NULL, completed_at TEXT NULL,
        state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'complete', 'error')),
        method TEXT NOT NULL, url TEXT NOT NULL, request_headers TEXT NOT NULL DEFAULT '[]',
        request_body BLOB NOT NULL DEFAULT X'', response_status INTEGER NULL,
        response_headers TEXT NOT NULL DEFAULT '[]', response_body BLOB NOT NULL DEFAULT X'',
        response_size INTEGER NOT NULL DEFAULT 0,
        response_body_truncated INTEGER NOT NULL DEFAULT 0 CHECK (response_body_truncated IN (0, 1)),
        error_stage TEXT NOT NULL DEFAULT '', error_summary TEXT NOT NULL DEFAULT '',
        correlation_nonce TEXT NOT NULL UNIQUE,
        correlation_claimed INTEGER NOT NULL DEFAULT 0 CHECK (correlation_claimed IN (0, 1)),
        peer_address TEXT NOT NULL DEFAULT '', target_addresses TEXT NOT NULL DEFAULT '[]'
    )""",
    """CREATE TABLE exchange_record (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, completed_at TEXT NULL,
        duration_ms REAL NULL, method TEXT NOT NULL, url TEXT NOT NULL DEFAULT '',
        url_provenance TEXT NOT NULL DEFAULT 'reconstructed', scheme TEXT NOT NULL DEFAULT '',
        host TEXT NOT NULL DEFAULT '', path TEXT NOT NULL, query_string TEXT NOT NULL DEFAULT '',
        request_headers TEXT NOT NULL DEFAULT '[]', request_body BLOB NOT NULL DEFAULT X'',
        request_content_type TEXT NOT NULL DEFAULT '', request_declared_size INTEGER NULL,
        request_observed_size INTEGER NOT NULL DEFAULT 0, request_captured_size INTEGER NOT NULL DEFAULT 0,
        request_body_truncated INTEGER NOT NULL DEFAULT 0 CHECK (request_body_truncated IN (0, 1)),
        request_body_incomplete INTEGER NOT NULL DEFAULT 0 CHECK (request_body_incomplete IN (0, 1)),
        client_addr TEXT NOT NULL DEFAULT '', response_status INTEGER NULL,
        response_headers TEXT NOT NULL DEFAULT '[]', response_body BLOB NOT NULL DEFAULT X'',
        response_size INTEGER NOT NULL DEFAULT 0,
        response_body_truncated INTEGER NOT NULL DEFAULT 0 CHECK (response_body_truncated IN (0, 1)),
        response_body_incomplete INTEGER NOT NULL DEFAULT 0 CHECK (response_body_incomplete IN (0, 1)),
        state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'complete', 'application_error')),
        error_summary TEXT NOT NULL DEFAULT '', correlation_diagnostic TEXT NOT NULL DEFAULT '',
        observed_replay_attempt_id INTEGER NULL UNIQUE REFERENCES replay_attempt(id) ON DELETE SET NULL
    )""",
    "CREATE INDEX exchange_record_order_idx ON exchange_record(created_at DESC, id DESC)",
    "CREATE INDEX replay_attempt_source_order_idx ON replay_attempt(source_exchange_id, submitted_at DESC, id DESC)",
)
