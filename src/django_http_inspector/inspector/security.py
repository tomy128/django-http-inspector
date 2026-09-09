import hmac
from ipaddress import ip_address, ip_network
from urllib.parse import urlsplit


def host_without_port(value):
    value = value.strip()
    if value.startswith("["):
        end = value.find("]")
        return value[: end + 1].lower() if end >= 0 else ""
    return value.rsplit(":", 1)[0].lower() if value.count(":") == 1 else value.lower()


def client_allowed(remote_addr, cidrs):
    try:
        address = ip_address(remote_addr)
        return any(address in ip_network(cidr, strict=False) for cidr in cidrs)
    except ValueError:
        return False


def request_allowed(environ, config):
    host = host_without_port(str(environ.get("HTTP_HOST", "")))
    allowed_hosts = {host_without_port(item) for item in config.inspector_allowed_hosts}
    return host in allowed_hosts and client_allowed(
        str(environ.get("REMOTE_ADDR", "")), config.inspector_allowed_client_cidrs
    )


def mutation_allowed(environ, token, submitted_token):
    if not hmac.compare_digest(str(token), str(submitted_token)):
        return False
    host = str(environ.get("HTTP_HOST", ""))
    expected_origin = f"{environ.get('wsgi.url_scheme', 'http')}://{host}"
    origin = environ.get("HTTP_ORIGIN")
    if origin:
        parsed = urlsplit(str(origin))
        if f"{parsed.scheme}://{parsed.netloc}" != expected_origin:
            return False
    fetch_site = environ.get("HTTP_SEC_FETCH_SITE")
    if fetch_site and fetch_site not in {"same-origin", "none"}:
        return False
    return True
