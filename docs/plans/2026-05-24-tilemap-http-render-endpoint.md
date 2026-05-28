# Plan — tilemap-service HTTP render endpoint BUILD

> **Spec:** [`docs/specs/2026-05-24-tilemap-http-render-endpoint.md`](../specs/2026-05-24-tilemap-http-render-endpoint.md)
> (ACCEPTED 2026-05-24 — PO sign-off "approve"; §11 6 checkboxes cleared).
> **Size:** L · **Mode:** default v2.2 (human-in-loop) · **Date:** 2026-05-24

## What this plan delivers

`POST /internal/v1/tilemaps/render` running inside `tilemap-service`,
launched via the new `serve` subcommand, with Bearer auth + RFC 7807
problem+json errors. Acceptance criteria from spec §9 (AC-HTTP-1 through
AC-HTTP-10) are the gate.

## Build chunks

Four chunks, dependency-ordered. **TDD**: failing test → implement →
`cargo test --workspace` green before the next. `cargo clippy --workspace
--all-targets -- -D warnings` clean at every boundary.

### Chunk 1 — Deps + skeleton (no logic)

Adds workspace pins for `axum`, `tower`, `tower-http`, plus member dep
entries. Creates empty `src/http/` module so the next chunks have a
home. Pure scaffold — no behavior change.

Files:

- `Cargo.toml` (mod) — `[workspace.dependencies]` adds:
  - `axum = "0.8"` (or whatever stable lands in this dependency window;
    use minimum-version requirements not =-pins)
  - `tower = "0.5"`
  - `tower-http = { version = "0.6", features = ["trace", "timeout"] }`
- `services/tilemap-service/Cargo.toml` (mod) — adds `axum.workspace =
  true`, `tower.workspace = true`, `tower-http.workspace = true`. Adds
  dev-deps: `reqwest` (already in workspace) for the integration test.
- `services/tilemap-service/src/http/mod.rs` (new) — `pub mod auth;`
  `pub mod error;` `pub mod render;` `pub mod router;` re-exports.
- `services/tilemap-service/src/lib.rs` (mod) — add `pub mod http;`.

Pass criteria: `cargo build -p tilemap-service` succeeds; no new test;
clippy clean.

### Chunk 2 — Problem details + auth middleware

Pure-data types + a Tower layer. No router yet.

Files:

- `services/tilemap-service/src/http/error.rs` (new):
  - `ProblemDetails { type_: String, title: String, status: u16, detail: String }`
    — RFC 7807 shape, `#[serde(rename = "type")]` for the URN key
  - `impl IntoResponse for ProblemDetails` — emits
    `application/problem+json`, sets status from `.status`
  - `impl From<crate::Error> for ProblemDetails` — the table from
    spec §3.4
  - Stable URN constants (`URN_BAD_REQUEST`, `URN_UNAUTHORIZED`,
    `URN_PLACEMENT`, `URN_EMPTY_ZONE`, `URN_DEPENDENCY_CYCLE`,
    `URN_MODIFICATOR`, `URN_CONFIG`, `URN_INTERNAL`)

- `services/tilemap-service/src/http/auth.rs` (new):
  - `AppState { internal_token: Arc<String> }`
  - `async fn require_bearer(State(state): State<AppState>, req: Request,
    next: Next) -> Result<Response, ProblemDetails>` — extracts the
    `Authorization` header, validates the `Bearer <token>` shape, does
    a constant-time byte compare against `state.internal_token`, returns
    401 problem+json on mismatch

Tests (in `error.rs` + `auth.rs` `#[cfg(test)] mod tests`):

- `problem_details_serializes_with_type_field_renamed` — round-trip JSON
  shows `"type"` not `"type_"`
- `crate_error_placement_maps_to_422_with_correct_urn`
- `crate_error_empty_zone_maps_to_422_with_correct_urn`
- `bearer_middleware_rejects_missing_authorization` — call middleware
  with no header → 401 + URN_UNAUTHORIZED
- `bearer_middleware_rejects_wrong_token`
- `bearer_middleware_accepts_exact_match`

Pass criteria: 6 unit tests green; clippy clean. Tests instantiate
middleware against a synthetic Request — no live server needed.

### Chunk 3 — Render handler + integration test

The core endpoint. CPU-bound `place_tilemap` wrapped in
`spawn_blocking` per spec §7.

Files:

- `services/tilemap-service/src/http/render.rs` (new):
  ```rust
  #[derive(Debug, Deserialize)]
  pub struct RenderRequest {
      pub template: TilemapTemplate,
      pub channel_id: ChannelId,
      pub tier: ChannelTier,
      pub grid_size: GridSize,
      pub seed: u64,
  }

  pub async fn render(
      State(_state): State<AppState>,
      Json(req): Json<RenderRequest>,
  ) -> Result<Json<TilemapView>, ProblemDetails> {
      let view = tokio::task::spawn_blocking(move || {
          crate::engine::place_tilemap(
              &req.template, req.channel_id, req.tier, req.grid_size,
              TilemapSeed(req.seed),
          )
      })
      .await
      .map_err(|_| ProblemDetails::internal("background task panicked"))??;
      Ok(Json(view))
  }
  ```

- `services/tilemap-service/src/http/router.rs` (new):
  ```rust
  pub fn build_router(state: AppState) -> axum::Router {
      use axum::middleware::from_fn_with_state;
      use axum::routing::post;
      Router::new()
          .route("/internal/v1/tilemaps/render", post(render))
          .layer(from_fn_with_state(state.clone(), require_bearer))
          .layer(TimeoutLayer::new(Duration::from_secs(30)))
          .with_state(state)
  }
  ```

- `services/tilemap-service/tests/http_integration.rs` (new) — spins up a
  server via `axum::serve` on a `tokio::net::TcpListener::bind("127.0.0.1:0")`
  (ephemeral port), then uses `reqwest` to:
  - **AC-HTTP-2**: send a valid request → 200 + TilemapView whose
    template_id matches
  - **AC-HTTP-3**: send without Authorization → 401 + URN_UNAUTHORIZED
  - **AC-HTTP-4**: send with wrong token → 401
  - **AC-HTTP-5**: send malformed body (missing `seed`) → 400
  - **AC-HTTP-6**: send a template with no zones → 422 EmptyZone
    (verify the error path actually fires; if `place_tilemap` accepts
    empty zones, use a different forced-failure shape — see "Risks"
    below)
  - **AC-HTTP-7**: send same request twice → byte-identical response
  - **AC-HTTP-8**: send template with `world_zone: Some(IceSnapshot)` vs
    same template+seed with `None` → responses differ

Pass criteria: 7 integration tests green; existing 405-test baseline
preserved; clippy clean.

### Chunk 4 — Serve subcommand + boot guard

Wire the router into `main.rs`. Add the fail-to-start guard for
`LOREWEAVE_INTERNAL_TOKEN`.

Files:

- `services/tilemap-service/src/main.rs` (mod):
  - Add `serve` to the subcommand match
  - `async fn run_serve() -> Result<()>` — reads `LOREWEAVE_INTERNAL_TOKEN`
    (anyhow::bail if missing); reads `TILEMAP_HTTP_BIND` (default
    `0.0.0.0:7100`); calls `tilemap_service::http::serve(...)`
- `services/tilemap-service/src/http/mod.rs` (mod) — add `pub async fn
  serve(bind: SocketAddr, internal_token: String) -> anyhow::Result<()>`
  bootstrap function

Tests:

- **AC-HTTP-1**: integration test that boots `serve` programmatically
  in a tokio task on `127.0.0.1:0`, makes one request, shuts down via a
  `tokio::sync::oneshot` cancel token. (Adapts the integration test
  harness from Chunk 3.)
- **AC-HTTP-9**: a unit test against the boot guard — `run_serve()` (or
  the env-reading helper) returns Err when `LOREWEAVE_INTERNAL_TOKEN` is
  unset. Use `std::env::set_var`/`remove_var` carefully (single test,
  marked `#[serial_test::serial]` if needed; or just call the helper
  with explicit args bypassing env).

Pass criteria: `serve` subcommand boots and serves; integration test
green; clippy clean.

## Test count delta

- Chunk 1: 0 new
- Chunk 2: +6 unit (error mapping + auth)
- Chunk 3: +7 integration
- Chunk 4: +1 boot guard

Total: ~14 new tests. Existing 405-test baseline (after world_inherit
batch) preserved throughout.

## Deferred (NOT in this BUILD)

- Multiple endpoints (regenerate-zone, edit-template, override-placement,
  etc.) — spec §2 explicitly out of scope
- Postgres persistence — Phase 4+
- Forge AdminAction handlers — Phase 4+
- DP integration — Phase 4+
- TLS — gateway concern
- OpenAPI spec generation — write by hand later when frontend track wires
  the consumer
- Token rotation / JWT — future enterprise concern

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| `place_tilemap` doesn't error on empty zones (AC-HTTP-6 forces an EmptyZone path that doesn't fire) | Probe live behavior before writing the test; if zero zones returns Ok, force EmptyZone via a different misconfiguration (a zone with no tiles assigned — depends on grid size / placement). Fall back: trigger DependencyCycle via modificator misconfig, swap AC-HTTP-6 accordingly. |
| `spawn_blocking` panic returns JoinError, not crate::Error | `error.rs` adds `ProblemDetails::internal(detail)` constructor; handler maps `JoinError` to 500 internal. |
| Integration test races (server not yet listening when client connects) | Use `tokio::net::TcpListener::bind("127.0.0.1:0").await` to bind FIRST, read the actual port via `.local_addr()`, then spawn the serve task — no race. |
| Tower middleware ordering subtle (auth layer placement) | Spec §6 layout puts `require_bearer` as middleware on the `/internal/v1/*` route group, not the whole router. If global middleware is simpler, audit at code-review time. |
| Axum 0.8 API drift from older docs | Pin to current stable; check `axum::middleware::from_fn_with_state` signature against the actual published version when adding the dep. |
| `LOREWEAVE_INTERNAL_TOKEN` env test pollutes other tests | Boot guard test takes the token as a function param rather than reading env; test calls with empty string to exercise the rejection path, avoiding env mutation. |

## Phase progression

| Phase | Status | Evidence target |
|---|---|---|
| CLARIFY | ✅ | PO 3-question answers 2026-05-24 |
| DESIGN | ✅ | spec ACCEPTED 2026-05-24 |
| REVIEW-DESIGN | ✅ | PO "approve" en bloc |
| PLAN | (this file) | 4 chunks + ACs + risks |
| BUILD | next | 4 chunks, TDD, each green before next |
| VERIFY | next | `cargo test --workspace` + `cargo clippy --workspace --all-targets -- -D warnings` |
| REVIEW-CODE | next | self-review pass — spec compliance + code quality |
| QC | next | spec §9 acceptance criteria check |
| POST-REVIEW | next | present to PO; await ack; `/review-impl` if requested |
| SESSION | next | SESSION_HANDOFF update |
| COMMIT | next | single commit, stage only changed files |
| RETRO | next | non-obvious lessons → SESSION_HANDOFF inline |
