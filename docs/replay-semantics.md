# Replay semantics

django-inspect replays the complete effective URL reconstructed at capture time. For WSGI this is derived from the application-visible scheme, Host, path, and original query string. Trusted proxy headers participate only when `REMOTE_ADDR` belongs to `TRUSTED_PROXY_CIDRS`.

Replay uses a real outbound HTTP connection. It does not call the Django application object directly and does not replace the destination with `127.0.0.1`.

## Necessary normalization

The following differences from the captured WSGI request are intentional:

- Hop-by-hop headers are removed.
- `Host` is generated from the target URL.
- `Content-Length` is generated from the captured body.
- `X-Django-Inspect-Replay` is replaced with a fresh correlation nonce.
- Redirects are returned as responses and are not followed.

Requests whose body was truncated, read incompletely, or failed while reading cannot be replayed.

Because WSGI servers may normalize paths and merge request headers, replay is semantically equivalent to the request observed by WSGI; it is not byte-for-byte network replay.
