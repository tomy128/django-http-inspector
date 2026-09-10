from dataclasses import dataclass
from ipaddress import ip_network
from os import PathLike
from pathlib import Path
from typing import Tuple

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@dataclass(frozen=True)
class InspectConfig:
    enabled: bool
    allow_remote: bool
    path: str
    capture_max_bytes: int
    max_records: int
    exclude_paths: Tuple[str, ...]
    trusted_proxy_cidrs: Tuple[str, ...]
    inspector_allowed_hosts: Tuple[str, ...]
    inspector_allowed_client_cidrs: Tuple[str, ...]
    replay_timeout: float
    sqlite_path: Path

    def is_inspector_path(self, path: str) -> bool:
        base = self.path.rstrip("/")
        return path == base or path.startswith(base + "/")

    def is_excluded_path(self, path: str) -> bool:
        return self.is_inspector_path(path) or any(
            path == prefix.rstrip("/") or path.startswith(prefix)
            for prefix in self.exclude_paths
        )


def _path(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.startswith("/"):
        raise ImproperlyConfigured(f"DJANGO_HTTP_INSPECTOR[{name!r}] must start with '/'.")
    return value.rstrip("/") + "/"


def _positive_number(value: object, name: str, number_type):
    if isinstance(value, bool) or not isinstance(value, number_type) or value <= 0:
        raise ImproperlyConfigured(f"DJANGO_HTTP_INSPECTOR[{name!r}] must be positive.")
    return value


def _boolean(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise ImproperlyConfigured(f"DJANGO_HTTP_INSPECTOR[{name!r}] must be a boolean.")
    return value


def load_config() -> InspectConfig:
    raw = getattr(settings, "DJANGO_HTTP_INSPECTOR", {})
    if not isinstance(raw, dict):
        raise ImproperlyConfigured("DJANGO_HTTP_INSPECTOR must be a dictionary.")

    allow_remote = _boolean(raw.get("ALLOW_REMOTE", False), "ALLOW_REMOTE")
    trusted = tuple(raw.get("TRUSTED_PROXY_CIDRS", ()))
    clients = tuple(raw.get("INSPECTOR_ALLOWED_CLIENT_CIDRS", ("127.0.0.0/8", "::1/128")))
    try:
        for cidr in trusted + clients:
            ip_network(cidr, strict=False)
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(f"Invalid django-http-inspector CIDR: {exc}") from exc
    if not allow_remote and any(not ip_network(cidr, strict=False).is_loopback for cidr in clients):
        raise ImproperlyConfigured(
            "MVP Inspector access is loopback-only; non-loopback authentication is not implemented."
        )

    hosts = tuple(raw.get("INSPECTOR_ALLOWED_HOSTS", ("localhost", "127.0.0.1", "[::1]")))
    if not hosts or not all(isinstance(host, str) and host for host in hosts):
        raise ImproperlyConfigured("INSPECTOR_ALLOWED_HOSTS must contain host names.")

    base_dir = Path(getattr(settings, "BASE_DIR", Path.cwd()))
    sqlite_value = raw.get("SQLITE_PATH", base_dir / ".django-http-inspector.sqlite3")
    if not isinstance(sqlite_value, (str, PathLike)) or not str(sqlite_value):
        raise ImproperlyConfigured("DJANGO_HTTP_INSPECTOR['SQLITE_PATH'] must be a non-empty path.")
    sqlite_path = Path(sqlite_value)
    if not sqlite_path.is_absolute():
        sqlite_path = base_dir / sqlite_path
    sqlite_path = sqlite_path.resolve()
    if sqlite_path.exists() and sqlite_path.is_dir():
        raise ImproperlyConfigured("DJANGO_HTTP_INSPECTOR['SQLITE_PATH'] must be a file, not a directory.")

    return InspectConfig(
        enabled=bool(raw.get("ENABLED", settings.DEBUG)),
        allow_remote=allow_remote,
        path=_path(raw.get("PATH", "/__inspect/"), "PATH"),
        capture_max_bytes=_positive_number(raw.get("CAPTURE_MAX_BYTES", 1024 * 1024), "CAPTURE_MAX_BYTES", int),
        max_records=_positive_number(raw.get("MAX_RECORDS", 1000), "MAX_RECORDS", int),
        exclude_paths=tuple(_path(p, "EXCLUDE_PATHS") for p in raw.get(
            "EXCLUDE_PATHS",
            ("/static/", "/favicon.ico", "/.well-known/appspecific/com.chrome.devtools.json"),
        )),
        trusted_proxy_cidrs=trusted,
        inspector_allowed_hosts=hosts,
        inspector_allowed_client_cidrs=clients,
        replay_timeout=float(_positive_number(raw.get("REPLAY_TIMEOUT", 10), "REPLAY_TIMEOUT", (int, float))),
        sqlite_path=sqlite_path,
    )
