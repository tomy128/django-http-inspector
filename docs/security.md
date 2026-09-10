# Security

django-http-inspector stores request and response bodies, headers, cookies, credentials, and personal data. Use it only in controlled development environments and configure short retention.

Multipart presentation does not redact text fields based on names such as password, token, or csrfmiddlewaretoken. File contents are not rendered, but remain stored in the Inspector SQLite database up to the configured capture limit and may be sent by Replay.

## Inspector access

- Disabled by default when `DEBUG=False`.
- The MVP accepts only loopback client addresses.
- Inspector routes validate `Host` independently because project middleware and `ALLOWED_HOSTS` do not protect them.
- State-changing actions require a random process token and validate available `Origin` and `Sec-Fetch-Site` headers.
- Captured content is escaped before HTML rendering.

The default mode intentionally rejects non-loopback client CIDRs because authenticated remote Inspector sessions are not implemented.

For trusted development networks, `ALLOW_REMOTE=True` intentionally bypasses Inspector Host and client CIDR checks. This mode has no authentication: every client that can reach the listening port can read captured secrets and obtain the token used by Clear and Replay actions. Enabling it emits a startup warning. Do not combine it with a public bind, port forwarding, a public tunnel, shared Wi-Fi, or any untrusted network.

## Replay

Replay is a deliberate outbound request and may access public, private, loopback, link-local, reserved, or metadata destinations. A persistent warning beside each replay action makes this risk visible; clicking the action sends immediately. Only HTTP and HTTPS URLs without userinfo are accepted.

Edit & Replay accepts headers and textual bodies only. Header syntax, count, line size, aggregate size, control characters, and ISO-8859-1 encodability are validated. Binary or incomplete captured bodies cannot be edited. Client payloads cannot override the captured method or URL, and unexpected fields are rejected before a replay attempt is created.

DNS is resolved before sending and the transport connects to a selected resolved IP while retaining the original hostname for HTTP Host and TLS SNI. Redirects are not followed. This prevents a second independent DNS lookup from silently changing a confirmed public destination into a private destination.

The correlation header is diagnostic, not authentication. Its random nonce can be claimed once together with the observed Exchange association in one atomic SQLite transaction.

## Operational guidance

- Never expose `/__inspect/` publicly.
- Do not use django-http-inspector in production.
- Do not commit or share `.django-http-inspector.sqlite3` or its `-wal` and `-shm` sidecars; all may contain sensitive captured data.
- Use Clear to remove Inspector history, or stop the process and delete the database plus sidecars to reset it completely.
- Remember that replaying mutations can charge cards, send email, write data, or enqueue jobs.
