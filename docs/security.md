# Security

django-inspect stores request and response bodies, headers, cookies, credentials, and personal data. Use it only in controlled development environments and configure short retention.

## Inspector access

- Disabled by default when `DEBUG=False`.
- The MVP accepts only loopback client addresses.
- Inspector routes validate `Host` independently because project middleware and `ALLOWED_HOSTS` do not protect them.
- State-changing actions require a random process token and validate available `Origin` and `Sec-Fetch-Site` headers.
- Captured content is escaped before HTML rendering.

The MVP intentionally rejects non-loopback client CIDRs because authentication for remotely exposed Inspector sessions is not implemented yet.

## Replay

Replay is a deliberate outbound request and may access public, private, loopback, link-local, reserved, or metadata destinations. The UI requires explicit acknowledgement before sending. Only HTTP and HTTPS URLs without userinfo are accepted.

DNS is resolved before sending and the transport connects to a selected resolved IP while retaining the original hostname for HTTP Host and TLS SNI. Redirects are not followed. This prevents a second independent DNS lookup from silently changing a confirmed public destination into a private destination.

The correlation header is diagnostic, not authentication. Its random nonce can be claimed once using an atomic database operation.

## Operational guidance

- Never expose `/__inspect/` publicly.
- Do not use django-inspect in production.
- Do not commit captured databases.
- Remember that replaying mutations can charge cards, send email, write data, or enqueue jobs.
