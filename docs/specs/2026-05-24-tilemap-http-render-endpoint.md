# Spec — tilemap-service HTTP render endpoint

> **Status:** ✅ ACCEPTED 2026-05-24 (PO sign-off "approve"; §11 6 checkboxes cleared en bloc). L task. Branch `mmo-rpg/zone-map-amaw`.
> **Workflow:** v2.2 default (human-in-loop).
> **CLARIFY answers (PO, 2026-05-24):**
> 1. Request body shape: full template in POST body (stateless; no Postgres yet)
> 2. Auth: internal-token Bearer via `LOREWEAVE_INTERNAL_TOKEN`, path `/internal/v1/...`
> 3. Error shape: RFC 7807 `problem+json`

## 1. Problem

tilemap-service today is a CLI binary (`classify` / `bootstrap` / `measure`
subcommands) — there's no HTTP surface for other services to call. The
pinned next-session agenda was originally framed as "Phase 4+: HTTP +
Postgres + Forge + DP". This spec scopes down to **HTTP only**, the
smallest backend slice that produces a curl-able endpoint without
requiring schema design, Forge handlers, or DP integration.

PO learning from the asset spike: *"đi xa nhưng không có gì kiểm chứng"*
(no consumer to validate against). Shipping HTTP unlocks the next slice
(frontend Phaser viewer) without locking in any database choice.

## 2. Scope

In scope (one L task):

1. New `axum`-based HTTP server inside tilemap-service, launched via a new
   `serve` subcommand on the existing `main.rs`.
2. One endpoint: `POST /internal/v1/tilemaps/render`.
3. Bearer token middleware sourced from `LOREWEAVE_INTERNAL_TOKEN`.
4. RFC 7807 `problem+json` error responses; `crate::Error` variants
   mapped to HTTP status codes.
5. End-to-end integration test that spins up the server on an ephemeral
   port + exercises the endpoint.

**Out of scope** (each its own future task):
- Postgres persistence — Phase 4+ proper
- Forge AdminAction handlers — Phase 4+ proper
- DP integration — Phase 4+ proper
- Multiple endpoints (regenerate-zone, edit-template, override-placement, etc.)
- TLS termination — handled by gateway/load-balancer
- API gateway routing — `api-gateway-bff` proxies later
- Rate limiting — gateway concern
- OpenAPI spec generation — write by hand, share with frontend track

## 3. Wire contract

### 3.1 Endpoint

```
POST /internal/v1/tilemaps/render HTTP/1.1
Host: tilemap-service:7100
Content-Type: application/json
Authorization: Bearer <LOREWEAVE_INTERNAL_TOKEN>

{ <RenderRequest JSON> }
```

### 3.2 RenderRequest

```jsonc
{
  "template": <TilemapTemplate>,    // full template JSON (existing schema)
  "channel_id": "ch_demo_001",       // string; embedded in seed derivation
  "tier": "country",                 // "continent" | "country" | "district" | "town"
  "grid_size": { "width": 64, "height": 64 },
  "seed": 305423872                  // u64; combined with channel into blake3 TilemapSeed
}
```

All fields required. Bare-minimum template — at least one `ZoneSpec` in `zones`.

### 3.3 Successful response — `200 OK`

```jsonc
Content-Type: application/json

{ <TilemapView JSON> }              // existing crate::types::TilemapView serde shape
```

### 3.4 Error response — RFC 7807 `application/problem+json`

```jsonc
Content-Type: application/problem+json

{
  "type": "urn:tilemap-service:error:placement",   // stable URN per category
  "title": "Zone placement failed",                 // short human-readable
  "status": 422,                                    // mirrored from HTTP status line
  "detail": "zone 'capital' was assigned no tiles"  // full crate::Error.to_string()
}
```

Status / type mapping:

| `crate::Error` variant | HTTP | Type URN |
|---|---:|---|
| Json (request body parse failure) | `400` | `urn:tilemap-service:error:bad-request` |
| (missing/invalid Bearer token) | `401` | `urn:tilemap-service:error:unauthorized` |
| Placement | `422` | `urn:tilemap-service:error:placement` |
| EmptyZone | `422` | `urn:tilemap-service:error:empty-zone` |
| DependencyCycle | `422` | `urn:tilemap-service:error:dependency-cycle` |
| Modificator | `422` | `urn:tilemap-service:error:modificator` |
| Config | `500` | `urn:tilemap-service:error:config` |
| Io | `500` | `urn:tilemap-service:error:internal` |
| Llm (not reachable on this endpoint) | `500` | `urn:tilemap-service:error:internal` |

Notes:
- `urn:tilemap-service:error:*` URNs are stable string keys — clients SHOULD
  match on them, not on `title` text.
- `detail` is the raw `Error::to_string()` — useful for debugging, may shift
  across revisions; clients SHOULD NOT regex-parse it.
- 401 is emitted by the auth middleware before the handler runs, so it
  never reaches `crate::Error` mapping.

## 4. Auth

Single shared secret in env: `LOREWEAVE_INTERNAL_TOKEN` (already required
by other tilemap-service subcommands). The server reads it once at
boot and stores in router state. Every `/internal/v1/*` request must
present `Authorization: Bearer <token>` with byte-exact match.

| Outcome | Status |
|---|---:|
| Missing `Authorization` header | `401` |
| Header present but not `Bearer <x>` form | `401` |
| Token present but byte-differs from env | `401` |
| Token matches | request proceeds |

**Hard requirement:** server fails to start if `LOREWEAVE_INTERNAL_TOKEN`
is unset. No silent dev-mode bypass.

**Out of scope this task:** token rotation, JWT, per-user auth. The
internal Bearer pattern matches `auth-service` / `book-service` /
`provider-registry-service`.

## 5. Server config

Env vars consumed by `serve` subcommand:

| Var | Required | Default | Purpose |
|---|:-:|---|---|
| `LOREWEAVE_INTERNAL_TOKEN` | ✅ | — | Bearer secret |
| `TILEMAP_HTTP_BIND` | ❌ | `0.0.0.0:7100` | bind address |
| `RUST_LOG` | ❌ | `info,tilemap_service=debug` | tracing filter (existing) |

7100 picked from the range other tilemap docs reference (auth-service 7080,
book-service 7081, sharing-service 7082, etc. — exact assignment lives in
docker-compose; can shift, not load-bearing here).

## 6. Module layout

```
services/tilemap-service/src/
├── http/                          (NEW)
│   ├── mod.rs                     router + state + serve()
│   ├── render.rs                  POST /internal/v1/tilemaps/render handler
│   ├── error.rs                   ProblemDetails + IntoResponse for crate::Error
│   └── auth.rs                    Bearer token middleware
└── main.rs                        (MOD) — add `serve` subcommand branch

tests/
└── http_integration.rs            (NEW) — boot server on ephemeral port, curl-equivalent
```

`http/auth.rs` exposes a `tower::Layer` (or `axum::middleware::from_fn`
closure) that consumes a `Bearer` and rejects mismatches with 401.

Router state:

```rust
#[derive(Clone)]
struct AppState {
    internal_token: String,   // sourced from env at boot
}
```

## 7. Concurrency, blocking, and timeouts

- `place_tilemap` is **CPU-bound + synchronous** (no async, no I/O). Calling
  it from an async handler would block the tokio reactor.
- Wrap in `tokio::task::spawn_blocking` so the handler stays cooperative.
- Add a server-side timeout layer (`tower::timeout::TimeoutLayer`,
  30 seconds) — large grids should finish well under this; a hung request
  surfaces as 504 (mapped to a problem+json with type
  `urn:tilemap-service:error:timeout` if we add the variant; for L task
  the default tower timeout response is acceptable, returning 500 with a
  generic body).

## 8. Backward compatibility

- Existing CLI subcommands (`classify`, `bootstrap`, `measure`) unchanged.
- `lib.rs` adds `pub mod http;` — additive, no removed surface.
- Existing tests untouched.
- `Cargo.toml` adds new deps (`axum`, `tower`, `tower-http`, `http`,
  `http-body-util` if needed for tests). Workspace pin lifts to root.

## 9. Acceptance criteria

| ID | Criterion |
|---|---|
| AC-HTTP-1 | `serve` subcommand binds, prints listening address, responds to SIGINT for clean shutdown. |
| AC-HTTP-2 | `POST /internal/v1/tilemaps/render` with a valid token + valid body returns 200 + `TilemapView` JSON whose `template_id` matches the request. |
| AC-HTTP-3 | Missing Bearer token → 401 + `problem+json` body whose `type` is `urn:tilemap-service:error:unauthorized`. |
| AC-HTTP-4 | Wrong Bearer token → 401 (same shape as AC-HTTP-3). |
| AC-HTTP-5 | Malformed request body (e.g. unknown field, wrong JSON shape) → 400 + problem+json. |
| AC-HTTP-6 | A template that triggers `EmptyZone` → 422 + problem+json whose `type` is `urn:tilemap-service:error:empty-zone`. |
| AC-HTTP-7 | Determinism preserved across the HTTP boundary: same request body twice → byte-identical response. |
| AC-HTTP-8 | World-inheritance path works through HTTP: a request whose template carries `world_zone: Some(IceSnapshot)` returns a `TilemapView` whose object placements differ from the same template+seed with `world_zone: None`. (Composition test — covers the bridge wiring at the HTTP layer.) |
| AC-HTTP-9 | Server fails to start (clean error message) if `LOREWEAVE_INTERNAL_TOKEN` is unset. |
| AC-HTTP-10 | Total new test count ≥ 8; existing 405-test baseline preserved. |

## 10. Compliance check

| Rule | This spec |
|---|---|
| Contract-first | ✅ spec frozen before frontend or downstream caller is written |
| Gateway invariant | ✅ path is `/internal/v1/...`; external traffic routes through `api-gateway-bff` later |
| Provider gateway invariant | ✅ N/A — this endpoint does not call any LLM |
| Language rule | ✅ Rust (existing tilemap-service language) |
| No hardcoded secrets | ✅ `LOREWEAVE_INTERNAL_TOKEN` via env; server fails to start if unset |
| No hardcoded model names | ✅ N/A |
| Each service owns its Postgres DB | ✅ N/A — this slice deliberately ships no DB |

## 11. PO sign-off checklist

- [ ] Endpoint path `/internal/v1/tilemaps/render` + verb `POST` are right
- [ ] Stateless full-template POST body (no Postgres) is right for this slice
- [ ] RFC 7807 `problem+json` is the right error shape for cross-service consumers
- [ ] AC-HTTP-8 (HTTP world-inheritance integration) is a useful gate, not over-scope
- [ ] Internal-token Bearer pattern matches LoreWeave conventions
- [ ] Fail-to-start on missing token (no dev-mode bypass) is correct
