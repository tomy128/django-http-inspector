import socket
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlsplit


METADATA_ADDRESSES = {"169.254.169.254", "fd00:ec2::254"}


class TargetError(ValueError):
    pass


@dataclass(frozen=True)
class ReplayTarget:
    url: str
    scheme: str
    hostname: str
    port: int
    request_target: str
    addresses: tuple
    risky: bool


def address_is_risky(value):
    address = ip_address(value)
    return (
        value in METADATA_ADDRESSES
        or address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
    )


def resolve_target(url):
    if any(ord(ch) < 32 for ch in url):
        raise TargetError("URL contains control characters.")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise TargetError("Only http and https URLs can be replayed.")
    if parsed.username is not None or parsed.password is not None:
        raise TargetError("URL userinfo is not allowed.")
    if not parsed.hostname:
        raise TargetError("URL has no hostname.")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise TargetError("URL has an invalid port.") from exc
    try:
        info = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise TargetError(f"DNS lookup failed: {exc}") from exc
    addresses = tuple(dict.fromkeys(item[4][0] for item in info))
    if not addresses:
        raise TargetError("DNS lookup returned no addresses.")
    path = parsed.path or "/"
    request_target = path + (("?" + parsed.query) if parsed.query else "")
    return ReplayTarget(
        url=url,
        scheme=parsed.scheme,
        hostname=parsed.hostname,
        port=port,
        request_target=request_target,
        addresses=addresses,
        risky=any(address_is_risky(address) for address in addresses),
    )
