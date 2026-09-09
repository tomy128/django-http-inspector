# Replay semantics

django-http-inspector replays the complete effective URL reconstructed at capture time. For WSGI this is derived from the application-visible scheme, Host, path, and original query string. Trusted proxy headers participate only when `REMOTE_ADDR` belongs to `TRUSTED_PROXY_CIDRS`.

Replay uses a real outbound HTTP connection. It does not call the Django application object directly and does not replace the destination with `127.0.0.1`.

## Necessary normalization

The following differences from the captured WSGI request are intentional:

- Hop-by-hop headers are removed.
- `Host` is generated from the target URL.
- `Content-Length` is generated from the captured body.
- `X-Django-HTTP-Inspector-Replay` is replaced with a fresh correlation nonce.
- Redirects are returned as responses and are not followed.

Requests whose body was truncated, read incompletely, or failed while reading cannot be replayed.

Equivalent replay sends the captured header/body snapshot. Edit & Replay may replace only the request headers and a text-decodable body; the original Exchange is never modified. The edited `Content-Type` determines body encoding. Empty bodies remain editable, but a non-empty edited body requires a textual media type. Both modes always reuse the captured method and complete URL.

Before network activity, a pending ReplayAttempt is committed to the Inspector's independent SQLite database. If that commit fails, no request is sent. The replay transport runs without an open database transaction. If saving the final outcome fails after the request was sent, the tool reports that persistence failure and never retries the HTTP request automatically.

When the replay returns through the wrapper, claiming its nonce and associating the new inbound Exchange happen in one transaction. A nonce can correlate at most one Exchange.

Because WSGI servers may normalize paths and merge request headers, replay is semantically equivalent to the request observed by WSGI; it is not byte-for-byte network replay.
