import http.client
import socket
import ssl

from django_inspect.capture.headers import replay_headers


class ReplayTransportError(Exception):
    def __init__(self, stage, message):
        super().__init__(message)
        self.stage = stage


class PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, port, pinned_address, timeout):
        super().__init__(host, port, timeout=timeout)
        self.pinned_address = pinned_address

    def connect(self):
        self.sock = socket.create_connection((self.pinned_address, self.port), self.timeout)


class PinnedHTTPSConnection(PinnedHTTPConnection):
    def __init__(self, host, port, pinned_address, timeout):
        super().__init__(host, port, pinned_address, timeout)
        self.context = ssl.create_default_context()

    def connect(self):
        raw = socket.create_connection((self.pinned_address, self.port), self.timeout)
        self.sock = self.context.wrap_socket(raw, server_hostname=self.host)


def send_request(target, method, headers, body, timeout, max_bytes, nonce):
    address = target.addresses[0]
    connection_class = PinnedHTTPSConnection if target.scheme == "https" else PinnedHTTPConnection
    connection = connection_class(target.hostname, target.port, address, timeout)
    try:
        connection.connect()
        peer = connection.sock.getpeername()[0]
        if ip_normalized(peer) != ip_normalized(address):
            raise ReplayTransportError("validation", "Connected peer did not match the pinned DNS result.")
        connection.putrequest(method, target.request_target, skip_host=True, skip_accept_encoding=True)
        host = target.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        default_port = 443 if target.scheme == "https" else 80
        if target.port != default_port:
            host = f"{host}:{target.port}"
        connection.putheader("Host", host)
        for name, value in replay_headers(headers):
            connection.putheader(name, value)
        connection.putheader("X-Django-Inspect-Replay", nonce)
        connection.putheader("Content-Length", str(len(body)))
        connection.endheaders(body)
        response = connection.getresponse()
        response_headers = [[name, value] for name, value in response.getheaders()]
        captured = bytearray()
        total = 0
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            remaining = max_bytes - len(captured)
            if remaining > 0:
                captured.extend(chunk[:remaining])
        return response.status, response_headers, bytes(captured), total, peer
    except socket.gaierror as exc:
        raise ReplayTransportError("dns", str(exc)) from exc
    except ssl.SSLError as exc:
        raise ReplayTransportError("tls", str(exc)) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise ReplayTransportError("timeout", str(exc)) from exc
    except (ConnectionError, OSError) as exc:
        raise ReplayTransportError("connect", str(exc)) from exc
    except http.client.HTTPException as exc:
        raise ReplayTransportError("read", str(exc)) from exc
    finally:
        connection.close()


def ip_normalized(value):
    import ipaddress

    return ipaddress.ip_address(value)
