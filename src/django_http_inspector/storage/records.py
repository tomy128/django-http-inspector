from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


def utc_now():
    return datetime.now(timezone.utc)


class ExchangeState:
    PENDING = "pending"
    COMPLETE = "complete"
    APPLICATION_ERROR = "application_error"


class ReplayState:
    PENDING = "pending"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class ExchangeRecord:
    State = ExchangeState

    id: Optional[int] = None
    created_at: datetime = field(default_factory=utc_now)
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    method: str = "GET"
    url: str = ""
    url_provenance: str = "reconstructed"
    scheme: str = ""
    host: str = ""
    path: str = "/"
    query_string: str = ""
    request_headers: List[List[str]] = field(default_factory=list)
    request_body: bytes = b""
    request_content_type: str = ""
    request_declared_size: Optional[int] = None
    request_observed_size: int = 0
    request_captured_size: int = 0
    request_body_truncated: bool = False
    request_body_incomplete: bool = False
    client_addr: str = ""
    response_status: Optional[int] = None
    response_headers: List[List[str]] = field(default_factory=list)
    response_body: bytes = b""
    response_size: int = 0
    response_body_truncated: bool = False
    response_body_incomplete: bool = False
    state: str = ExchangeState.PENDING
    error_summary: str = ""
    correlation_diagnostic: str = ""
    observed_replay_attempt_id: Optional[int] = None


@dataclass
class ReplayAttemptRecord:
    State = ReplayState

    id: Optional[int] = None
    source_exchange_id: Optional[int] = None
    mode: str = "equivalent"
    submitted_at: datetime = field(default_factory=utc_now)
    completed_at: Optional[datetime] = None
    state: str = ReplayState.PENDING
    method: str = "GET"
    url: str = ""
    request_headers: List[List[str]] = field(default_factory=list)
    request_body: bytes = b""
    response_status: Optional[int] = None
    response_headers: List[List[str]] = field(default_factory=list)
    response_body: bytes = b""
    response_size: int = 0
    response_body_truncated: bool = False
    error_stage: str = ""
    error_summary: str = ""
    correlation_nonce: str = ""
    correlation_claimed: bool = False
    peer_address: str = ""
    target_addresses: List[str] = field(default_factory=list)
    persistence_error: str = ""
    network_attempted: bool = False
