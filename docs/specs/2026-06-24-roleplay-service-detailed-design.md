# Detailed Design — roleplay-service (Rust) v1 implementation seams

- **Date:** 2026-06-24
- **Scope:** Resolve the 5 implementation seams that have no Rust precedent so PLAN/BUILD is mechanical. Architecture, data model, tenancy, scope, and edge cases live in [the spec](2026-06-24-roleplay-scripted-acting.md). This doc is **how**, grounded in the real codebase patterns.
- **Key fact:** roleplay-service is the **first user-facing Rust service** — world/travel/tilemap are internal kernel services (their `require_bearer` checks the *internal token*, not a user JWT). So the user-JWT seam is net-new; the generic HTTP infra is extracted into a shared kit (§0.5).

---

## 0.5 Shared kit — `crates/service-http` (extract the duplicated HTTP infra)

The axum skeleton is at its **third copy** (tilemap, world, now roleplay) — rule-of-three: extract. And `require_user` is a **security primitive** that must live once, not be copy-pasted across a growing Rust fleet. The kit provides generic plumbing; each service still owns its routes/handlers/error-enum/config-struct.

**`crates/service-http` provides:**
```
serve(addr, router) + graceful shutdown            # tokio signal handling (from tilemap http/mod.rs)
health::routes() -> Router                          # /livez /readyz (DB-aware) /metrics
ProblemDetails (RFC 7807) + IntoResponse + `message` field   # FE-readable (apiJson reads err.message)
require_internal_token  middleware                  # X-Internal-Token exact match
require_user            middleware → Extension<UserId>       # JWT HS256 (the §3 primitive)
trace::layer()  +  init_tracing()                   # JSON logs (service+trace_id) + X-Trace-Id in/out
metrics::layer()                                    # request count/latency on /metrics
config::require_env(keys) / optional_env(key, default)       # fail-closed env reading
db::init(url, migrator) -> PgPool                   # PgPoolOptions + sqlx::migrate! (the §4 pattern)
```
**Consumers:** roleplay-service is the first (built on it from day one — validates it by real use). tilemap/world migrate **opportunistically** when next touched — NOT a forced refactor now (don't destabilize the kernel services).

**Why the additions over the bare tilemap copy** (the standardization sweep): JSON logging + `X-Trace-Id` propagation so the Rust hop stitches into the platform's cross-service traces (chat→knowledge already propagate it); the `message` field so RFC-7807 errors surface in the FE instead of bare `statusText`; `db::init` so the next per-service-DB Rust service copies the migration pattern, not reinvents it.

---

## 1. Service skeleton (seam #5) — build on `crates/service-http` + mirror `tilemap-service`

**Workspace:** add `"services/roleplay-service"` to `members` in the root [Cargo.toml](../../Cargo.toml). All deps inherit via `{ workspace = true }`.

**`services/roleplay-service/Cargo.toml`** (copy tilemap's; bin+lib named `roleplay_service`):
```toml
[package]
name = "roleplay-service"
version = "0.1.0-v1"
edition.workspace = true
rust-version.workspace = true
[dependencies]
tokio = { workspace = true }
axum = { workspace = true }
tower = { workspace = true }
tower-http = { workspace = true }
sqlx = { workspace = true }              # NEEDS the "chrono" feature added (see §11)
serde = { workspace = true }
serde_json = { workspace = true }
thiserror = { workspace = true }
anyhow = { workspace = true }
uuid = { workspace = true }
reqwest = { workspace = true }           # outbound → chat-service internal
tracing = { workspace = true }
chrono = { workspace = true }            # typed TIMESTAMPTZ in models
service-http = { path = "../../crates/service-http" }   # serve/health/auth/trace/errors/db (§0.5)
[dev-dependencies]
wiremock = { workspace = true }
tokio = { workspace = true }
```
`jsonwebtoken` + `tracing-subscriber` are pulled in **by the kit**, not directly. roleplay-service's `src/http/auth.rs` shrinks to just `require_user` re-exported from the kit + the `UserId` extension.

**`src/` layout** (mirrors tilemap):
```
src/main.rs            # #[tokio::main]; read env; run migrations; http::serve(bind, AppState)
src/lib.rs             # pub mod http; config; db; models; handlers; error
src/config.rs          # Config::from_env() — fail-closed on missing secrets (§3 pattern)
src/db.rs              # PgPoolOptions::new().max_connections(20).connect(DATABASE_URL) + sqlx::migrate!
src/error.rs           # thiserror Error enum → ProblemDetails (RFC 7807, copy tilemap http/error.rs)
src/http/mod.rs        # serve() + graceful shutdown (copy tilemap)
src/http/router.rs     # build_router(state): user-JWT group + internal group + probes
src/http/auth.rs       # AppState + require_user (NEW, §3) + require_internal middlewares
src/models.rs          # Script, Scenario(charter superset), Scorecard mirrors of the API/DDL
src/handlers/scripts.rs   # CRUD
src/handlers/start.rs     # start-orchestration (§7)
migrations/0001_init.sql  # roleplay_scripts + rp_sessions + rp_memory + System seed (§4)
```

**Dockerfile + compose:** copy [tilemap Dockerfile](../../services/tilemap-service/Dockerfile) (multi-stage, build context = repo root, `debian:bookworm-slim`, `USER nobody:nogroup`); rename binary/paths to `roleplay-service`. Compose entry mirrors tilemap: `INTERNAL_SERVICE_TOKEN`, `DATABASE_URL`, `JWT_SECRET`, `CHAT_SERVICE_URL`, `ROLEPLAY_HTTP_BIND=0.0.0.0:7110`, healthcheck `wget /livez`, **host port 8221** (next free after tilemap 8220), internal 7110. **language-rule.yaml:78** `roleplay-service: missing`→`rust`.

---

## 2. HTTP + axum (seam #2) — copy tilemap, two auth groups

`build_router` ([tilemap router.rs](../../services/tilemap-service/src/http/router.rs) pattern), but **two** auth-gated groups instead of one:
```rust
pub fn build_router(state: AppState) -> Router {
    let user = Router::new()                                  // user-facing, JWT
        .route("/v1/roleplay/scripts", get(list).post(create))
        .route("/v1/roleplay/scripts/:id", get(get_one).patch(patch).delete(del))
        .route("/v1/roleplay/scripts/:id/start", post(start))
        .layer(from_fn_with_state(state.clone(), require_user));   // §3
    let internal = Router::new()                              // (none in v1; reserved)
        .layer(from_fn_with_state(state.clone(), require_internal));
    let probes = Router::new().route("/livez", get(livez)).route("/readyz", get(readyz));
    Router::new().merge(user).merge(internal).merge(probes)
        .layer(cors_layer()).layer(DefaultBodyLimit::max(MAX_BODY))
        .layer(TimeoutLayer::with_status_code(StatusCode::GATEWAY_TIMEOUT, Duration::from_secs(30)))
        .with_state(state)
}
```
- `serve()` + `shutdown_signal()` + `/livez`/`/readyz`: copy tilemap [http/mod.rs](../../services/tilemap-service/src/http/mod.rs) verbatim.
- **Errors:** copy tilemap's `ProblemDetails` (RFC 7807); map `Error::NotFound→404`, `Unauthorized→401`, `Forbidden→403`, `Conflict→409`, `BadRequest→400`, else 500. Handlers return `Result<Json<T>, ProblemDetails>`.
- `AppState { pool: PgPool, jwt_secret: Vec<u8>, internal_token: String, chat_url: String, http: reqwest::Client }`.

---

## 3. User-facing JWT auth (seam #1) — NEW; contract from book-service

The Go contract to mirror ([book-service server.go:321 `requireUserID`](../../services/book-service/internal/api/server.go#L321)): `Authorization: Bearer`, **HS256**, secret = `JWT_SECRET`, `sub` claim → user_id UUID. Rust equivalent with `jsonwebtoken`:

```rust
#[derive(serde::Deserialize)]
struct Claims { sub: String }   // RegisteredClaims subset

pub async fn require_user(State(s): State<AppState>, mut req: Request, next: Next)
    -> Result<Response, ProblemDetails> {
    let tok = req.headers().get(AUTHORIZATION).and_then(|h| h.to_str().ok())
        .and_then(|h| h.strip_prefix("Bearer "))
        .ok_or_else(|| ProblemDetails::unauthorized("missing bearer"))?;
    let mut val = Validation::new(Algorithm::HS256);
    val.validate_exp = true;                                  // matches Go default (exp checked)
    val.set_required_spec_claims(&["sub"]);
    let data = decode::<Claims>(tok, &DecodingKey::from_secret(&s.jwt_secret), &val)
        .map_err(|_| ProblemDetails::unauthorized("invalid token"))?;
    let user_id = Uuid::parse_str(&data.claims.sub)
        .map_err(|_| ProblemDetails::unauthorized("sub not a uuid"))?;
    req.extensions_mut().insert(UserId(user_id));             // handlers read via Extension<UserId>
    Ok(next.run(req).await)
}
```
- Handlers take `Extension(UserId(uid)): Extension<UserId>` — identity is **always** the JWT, never the body (INV-T2). Every script query filters `owner_user_id` (System rows = `owner_user_id IS NULL`, read-only).
- **`require_internal`** = exact-match on `X-Internal-Token` (copy tilemap's `require_bearer`, but keyed on the internal-token header) — reserved; no v1 inbound internal routes.
- **Gateway passthrough:** [api-gateway-bff](../../services/api-gateway-bff/src/gateway-setup.ts) forwards the `Authorization` header (http-proxy-middleware default), and like book-service, **roleplay-service validates the JWT itself** — the gateway does not pre-auth. §8 wires the proxy.

---

## 4. DB + migrations (seam #5) — establish the per-service-DB pattern

The kernel services use per-reality `.sql` files applied by tests/sidecars — **wrong fit** for `loreweave_roleplay` (a normal platform-plane per-service DB like `loreweave_chat`). roleplay-service **establishes the clean pattern**: `sqlx::migrate!()` at startup.

```rust
// src/db.rs
pub async fn init(url: &str) -> anyhow::Result<PgPool> {
    let pool = PgPoolOptions::new().max_connections(20).connect(url).await?;
    sqlx::migrate!("./migrations").run(&pool).await?;   // runs services/roleplay-service/migrations/*.sql
    Ok(pool)
}
```
**`migrations/0001_init.sql`** = the spec §3 schema:
```sql
CREATE TABLE roleplay_scripts ( script_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id UUID, tier VARCHAR(10) NOT NULL DEFAULT 'user', code VARCHAR(100) NOT NULL,
  name VARCHAR(255) NOT NULL, description TEXT, system_prompt TEXT NOT NULL,
  model_source VARCHAR(20), model_ref UUID, rubric JSONB, scenario JSONB NOT NULL DEFAULT '{}',
  genre VARCHAR(40) NOT NULL DEFAULT 'roleplay', book_id UUID, reality_id UUID,
  attachment_key VARCHAR(512), is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT rp_tier_owner_chk CHECK (
    (tier='system' AND owner_user_id IS NULL) OR
    (tier='user'   AND owner_user_id IS NOT NULL AND book_id IS NULL) OR
    (tier='book'   AND owner_user_id IS NOT NULL AND book_id IS NOT NULL)) );
CREATE UNIQUE INDEX uq_rp_system_code ON roleplay_scripts(code) WHERE owner_user_id IS NULL;
CREATE UNIQUE INDEX uq_rp_user_code   ON roleplay_scripts(owner_user_id, book_id, code)
  NULLS NOT DISTINCT WHERE owner_user_id IS NOT NULL;
CREATE TABLE rp_sessions ( session_id UUID PRIMARY KEY, script_id UUID NOT NULL REFERENCES roleplay_scripts,
  owner_user_id UUID NOT NULL, reality_id UUID, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  debrief_output_id UUID );
CREATE TABLE rp_memory ( session_id UUID PRIMARY KEY REFERENCES rp_sessions ON DELETE CASCADE,
  charter JSONB NOT NULL, state JSONB NOT NULL DEFAULT '{"phase":"","covered":[]}',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now() );
-- System seed: idempotent, mirrors chat-service M7 seed (3 presets, genre='interview' + roleplay)
INSERT INTO roleplay_scripts (owner_user_id, tier, code, name, description, system_prompt, scenario, genre)
VALUES (NULL,'system','faang_swe', ... ), ...  ON CONFLICT (code) WHERE owner_user_id IS NULL DO NOTHING;
```
- `NULLS NOT DISTINCT` (PG15+) makes `(owner,NULL-book,code)` unique — *the per-book index fix*.
- `gen_random_uuid()` (pgcrypto) — confirm extension; chat uses `uuidv7()`, available in this PG. Use whichever the cluster has.
- **v1 writes `tier` ∈ {system, user} only.** The `book` tier (roleplaying a character *from your book* — cast/lore pulled from glossary) is **deferred** with glossary anchoring + the Rust E0 grant client. The `book_id`/`reality_id` columns + the CHECK's `book` case are **forward-schema** (additive later, no migration). So v1 needs no glossary reads and no grant SDK.
- Pool + migrations via the kit: `service_http::db::init(DATABASE_URL, sqlx::migrate!("./migrations"))`.

---

## 5. chat-service internal create-session (seam #3) — Python, mirror `internal.py`

Add to chat-service [internal.py](../../services/chat-service/app/routers/internal.py) (already has `require_internal_token`):
```python
@router.post("/sessions", dependencies=[Depends(require_internal_token)], status_code=201)
async def internal_create_session(body: InternalCreateSession, db=Depends(get_db)) -> dict:
    row = await db.fetchrow("""
        INSERT INTO chat_sessions (owner_user_id,title,model_source,model_ref,system_prompt,
          project_id,working_memory_seed)
        VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb) RETURNING session_id
    """, body.owner_user_id, body.title, body.model_source, body.model_ref,
        body.system_prompt, None, json.dumps(body.working_memory_seed))
    return {"session_id": str(row["session_id"])}
```
- `InternalCreateSession {owner_user_id, title, model_source, model_ref, system_prompt, working_memory_seed: dict}`.
- This is the **exact INSERT** already in `templates.py /start` — extract it; `/start` then either calls this internally or is removed when scripts move (§6). The owner is **in the body** here because the caller (roleplay-service) already JWT-verified the user — the internal-token gates the trust boundary.
- roleplay-service calls it via reqwest (copy world-service [http_provider.rs](../../services/world-service/src/embedding_queue/live/http_provider.rs) pattern): `POST {CHAT_SERVICE_URL}/internal/chat/sessions` + `X-Internal-Token`.

---

## 6. Migration / re-home (seam #4)

1. **System presets:** re-seeded fresh by `0001_init.sql` (idempotent) — no copy needed.
2. **User scripts:** test data only today → none to move. (If prod rows existed: a one-shot `psql` `\copy` from `loreweave_chat.session_templates` → `loreweave_roleplay.roleplay_scripts` mapping columns + `genre='interview'`.)
3. **Transition safety (EC-10):** keep chat-service `/v1/chat/templates*` + `/evaluate` LIVE until roleplay-service passes its tests + a re-run of the **M7 browser smoke** against `/v1/roleplay`. Then re-point the FE and retire the chat-service script endpoints. No flag-day.

---

## 7. Start-orchestration flow (ties it together)

`POST /v1/roleplay/scripts/{id}/start` (user JWT → `uid`):
1. Load script visible to `uid` (`owner_user_id IS NULL OR owner_user_id=uid`); 404 else.
2. Resolve `model_source/ref` (body override > script default); 400 if none.
3. Freeze `charter` from `scenario` (premise→goal, beats→checklist, phases, language, improv_freedom).
4. **chat first (EC-3):** reqwest → chat-service `POST /internal/chat/sessions` `{owner_user_id:uid, title, model_source, model_ref, system_prompt, working_memory_seed:charter}` → `session_id`.
5. Insert `rp_sessions(session_id, script_id, uid)` + `rp_memory(session_id, charter, state={})` (one tx; **validated by a read-back test** per spec §10.6 — written now, the live anchor still comes from the chat seed).
6. Return `{session_id}`. FE opens it in `ChatView` (talks `/v1/chat`); anchoring runs from the seed.

Idempotent by `session_id`; if step 5 fails the chat session + seed still exist (M3 anchors), and a reconcile can backfill `rp_memory` — never a charter without a session.

---

## 8. Gateway wiring (api-gateway-bff)

Mirror the `chatProxy` block in [gateway-setup.ts](../../services/api-gateway-bff/src/gateway-setup.ts):
```ts
const roleplayProxy = createProxyMiddleware({ target: urls.roleplayUrl, changeOrigin: true,
  pathFilter: (p: string) => p.startsWith('/v1/roleplay') });
// ...in the dispatch chain:
if (req.path.startsWith('/v1/roleplay')) return roleplayProxyFn(req, res, next);
```
+ `roleplayUrl: string` in the config (env `ROLEPLAY_SERVICE_URL=http://roleplay-service:7110`). Headers (incl. `Authorization`) pass through; roleplay-service validates the JWT (§3).

---

## 9. New workspace deps (§11)

Add to root [Cargo.toml](../../Cargo.toml) `[workspace.dependencies]`:
```toml
jsonwebtoken = "9"
chrono = { version = "0.4", features = ["serde"] }
```
and add the `"chrono"` feature to the workspace `sqlx` entry (for `TIMESTAMPTZ` → `DateTime<Utc>`). `gen_random_uuid`/`uuidv7` come from the DB, not Rust.

## 10. Test plan (mirror tilemap/world-service)

- **Unit** (`#[cfg(test)]`): `require_user` (valid/expired/bad-sig/non-uuid-sub → 401); tenancy (System write → 404; cross-user → 404); charter-from-scenario mapping; per-book unique constraint logic.
- **Integration** (`tests/`, `wiremock`): start-orchestration with a mocked chat-service `/internal/chat/sessions` → asserts the seed payload + `rp_sessions`/`rp_memory` round-trip (the spec §10.6 read-back validation).
- **Live-smoke** (gated on `LOREWEAVE_TEST_PG_URL`): apply `0001_init.sql`; full start against a real chat-service; re-run the **M7 browser smoke** end-to-end on `/v1/roleplay`.

## 11. Build manifest (for PLAN → R0/R1)

New files: `services/roleplay-service/{Cargo.toml, Dockerfile, src/**, migrations/0001_init.sql}`. Edits: root `Cargo.toml` (member + 2 deps + sqlx feature), `infra/docker-compose.yml` (service + port 8221), `contracts/language-rule.yaml` (→rust), `api-gateway-bff/src/{gateway-setup.ts, config}` (proxy + url), chat-service `internal.py` (+`InternalCreateSession` model) — and at R2, the FE re-point + the chat-service script-endpoint retirement.
