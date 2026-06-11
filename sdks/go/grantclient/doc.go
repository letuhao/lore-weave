// Package grantclient is the shared Go client every service uses to resolve a
// (user, book) permission against book-service — the single grant authority for
// the E0 collaboration-permissions epic.
//
// book-service owns both `books` and `book_collaborators` and exposes
// GET /internal/books/{book_id}/access?user_id=… which always returns
// 200 {"grant_level": "none|view|edit|manage|owner"} — `none` covers both a
// missing book and no-grant, so the endpoint is never an existence oracle (R4).
//
// # Caching
//
// ResolveGrant is backed by a short-TTL cache that stores ONLY positive grants
// (level > none), mirroring glossary-service's ownerCache:
//
//   - A freshly granted user is never denied for the TTL window (none is never
//     cached, so the next call re-fetches and sees the new grant immediately).
//   - A revoked or downgraded grant takes effect within the TTL (positives
//     expire; the next call re-fetches the lower level). v1 TTL is 60s, which
//     satisfies AC4 (revoke effective ≤60s). Instant-revoke (Redis invalidate)
//     is deferred to v1.1.
//
// # Fail-closed
//
// If book-service is unreachable or returns a non-200, ownership is UNKNOWN, so
// ResolveGrant returns (GrantNone, ErrUnavailable) — callers deny rather than
// assume access. Errors are never cached.
//
// # Tracing
//
// NewClient defaults to http.DefaultTransport. A caller that wants W3C trace
// propagation injects its own instrumented RoundTripper (e.g.
// observability.HTTPTransport(nil)) via Options.Transport — matching the
// "caller owns instrumentation when supplied" convention used by the llmgw SDK.
//
// Construct ONE Client per process at startup and share it across goroutines;
// the client and its cache are goroutine-safe.
package grantclient
