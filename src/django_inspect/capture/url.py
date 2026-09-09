from ipaddress import ip_address, ip_network
from urllib.parse import quote


def _trusted(remote_addr, cidrs):
    try:
        address = ip_address(remote_addr)
        return any(address in ip_network(cidr, strict=False) for cidr in cidrs)
    except ValueError:
        return False


def _forwarded(environ):
    value = environ.get("HTTP_FORWARDED", "")
    if not value:
        return None, None
    nearest = value.split(",")[-1]
    parts = {}
    for item in nearest.split(";"):
        key, separator, raw = item.strip().partition("=")
        if separator:
            parts[key.lower()] = raw.strip().strip('"')
    return parts.get("proto"), parts.get("host")


def build_url(environ, trusted_proxy_cidrs=()):
    scheme = str(environ.get("wsgi.url_scheme", "http")).lower()
    host = str(environ.get("HTTP_HOST") or "")
    provenance = "reconstructed"
    if _trusted(str(environ.get("REMOTE_ADDR", "")), trusted_proxy_cidrs):
        forwarded_scheme, forwarded_host = _forwarded(environ)
        scheme = forwarded_scheme or str(environ.get("HTTP_X_FORWARDED_PROTO", "")).split(",")[-1].strip() or scheme
        host = forwarded_host or str(environ.get("HTTP_X_FORWARDED_HOST", "")).split(",")[-1].strip() or host
        provenance = "trusted_proxy"
    if scheme not in {"http", "https"} or not host or any(ch in host for ch in "\r\n/@"):
        return "", scheme, host, provenance

    raw_uri = environ.get("RAW_URI") or environ.get("REQUEST_URI")
    if raw_uri:
        target = str(raw_uri)
        provenance = "server_specific"
        if not target.startswith("/"):
            target = "/" + target
    else:
        script = quote(str(environ.get("SCRIPT_NAME", "")), safe="/%:@")
        path = quote(str(environ.get("PATH_INFO", "/")), safe="/%:@")
        target = script + path
        query = str(environ.get("QUERY_STRING", ""))
        if query:
            target += "?" + query
    return f"{scheme}://{host}{target}", scheme, host, provenance
