# tilemap-service — DESIGN.md (Phase 0a)

> **Status:** DRAFT 2026-05-14 (Phase 0a scaffold + SDK extraction post-`/review-impl`).
> **Source spec:** [`docs/03_planning/LLM_MMO_RPG/features/00_tilemap/`](../../docs/03_planning/LLM_MMO_RPG/features/00_tilemap/) (TMP_001..TMP_008b CANDIDATE-LOCK 2026-05-13).
> **Goal:** PoC validation of the TMP_008/TMP_008b LLM contract empirically. First Rust microservice in the LoreWeave monorepo.
> **Update 2026-05-14 (post-`/review-impl`):** LLM gateway client has been **extracted** to [`sdks/rust/loreweave_llm`](../../sdks/rust/loreweave_llm) as the first Rust SDK in the monorepo. tilemap-service depends on the SDK as a workspace path member. Module layout in §2 below reflects post-extraction state.

---

## 1. Goal + non-goals for Phase 0a

### Goal

Land a compiling Rust scaffold for `services/tilemap-service/` that:
- Mirrors the TMP_001 §2 domain types (ChannelTier, ZoneRole, PassageKind, TileState, TilemapTemplate stub, TilemapView stub) in Rust.
- Defines a blake3-based deterministic seed helper per TMP-A4 (replay-determinism axiom).
- Defines a stub LLM gateway HTTP client mirroring the `contracts/api/llm-gateway/v1/openapi.yaml` `StreamRequest` shape (types + reqwest client signatures, **no actual network call this session**).
- Has one compiling smoke test that round-trips a `TilemapView` JSON.
- Ships a multi-stage Dockerfile + README documenting PoC scope, known limitations, and the Phase 0a → 0b roadmap.

### Non-goals (Phase 0a)

These are explicitly deferred — Phase 0b or later:

| Non-goal | Why deferred |
|---|---|
| Real network call to the gateway | Phase 0b — requires provider-registry-service running + lmstudio registered as platform_model. |
| Actual algorithm impl (Fruchterman-Reingold zone placer, modificator pipeline, Penrose tiling) | Phase 1+ — each is non-trivial; Phase 0a is scaffold-only. |
| DP-K1..K12 SDK integration | Phase 2+ — DP SDK is itself unbuilt (only locked design). Mock at PoC boundary; production wiring later. |
| HTTP server surface (other services calling tilemap-service) | Phase 2+ — PoC is a CLI binary that runs against fixtures. |
| Channel subscribe (DP-Ch24 map_layout deltas → re-derive child_cell_anchors) | Phase 2+ — needs DP runtime. |
| Forge AdminAction handlers (Forge:RegenTilemap, Forge:EditTemplate, Forge:OverridePlacement) | Phase 2+ — needs HTTP server + DP write. |
| Postgres persistence | Phase 2+ — PoC stays in-memory. |
| Anthropic prompt-caching (`cache_control`) empirical validation | **Permanent limitation of Path A**: the LLM gateway does NOT expose Anthropic-specific `cache_control`; the SDK's `tools` field is generic. Surface this as a TMP_008b finding back to design. |

---

## 2. Module decomposition

Workspace layout (single Cargo workspace at repo root; first Rust workspace in the monorepo):

```
<repo-root>/
├── Cargo.toml                          (NEW: [workspace] + shared [workspace.dependencies])
├── sdks/rust/loreweave_llm/            (NEW: first Rust SDK; mirror of sdks/python/loreweave_llm)
│   ├── Cargo.toml
│   ├── README.md
│   ├── src/{lib,client,errors,models}.rs
│   └── tests/wire_format.rs            (17 wire-format conformance tests)
└── services/tilemap-service/           (this service)
    ├── Cargo.toml                      (depends on loreweave_llm path member)
    ├── Dockerfile
    ├── README.md
    ├── DESIGN.md                       (this file)
    ├── src/
    │   ├── main.rs                     (binary entry — CLI invocation)
    │   ├── lib.rs                      (library entry; re-exports loreweave_llm as `llm`)
    │   ├── error.rs                    (top-level Error enum forwarding LlmError via thiserror)
    │   ├── seed.rs                     (TMP-A4 blake3 seed helper)
    │   └── types/
    │       ├── mod.rs
    │       ├── channel.rs              (ChannelTier enum + ChannelId newtype stub)
    │       ├── tilemap.rs              (TilemapView struct stub, ZoneRuntime, TileCoord, GridSize)
    │       ├── template.rs             (TilemapTemplate struct stub, ZoneSpec stub, TilemapTemplateId)
    │       ├── zone.rs                 (ZoneRole enum, ZoneEdge, PassageKind enum)
    │       ├── tile.rs                 (TerrainKind enum, TileState enum)
    │       └── object.rs               (TilemapObjectKind enum, TilemapObjectPlacement)
    └── tests/
        └── smoke.rs                    (5 TMP-specific tests: TilemapView roundtrip, seed determinism, TMP-A1 cell exclusion, hex Display)
```

The original `services/tilemap-service/src/llm/` module from the initial Phase 0a draft was **promoted out** to `sdks/rust/loreweave_llm/` so any future Rust service can depend on the same gateway client. tilemap-service consumes the SDK via a workspace path dependency and re-exports it at the lib boundary (`pub use loreweave_llm as llm`).

**Rationale:**
- `types/` split per-concern (channel/tilemap/template/zone/tile/object) instead of one mega-module → keeps files <200 lines; matches TMP_001 §2's natural decomposition.
- **SDK extraction (`sdks/rust/loreweave_llm/`)** — the LLM gateway client is reusable across any future Rust service; keeping it in-service would force the next Rust service to reimplement. Promoted at the `/review-impl` cycle once the contract was validated against the openapi.
- **Cargo workspace at repo root** — shared `target/` (one cache, not N), single `Cargo.lock` (deps consistent across crates), `cargo build/test/clippy --workspace` semantics. Standard Rust monorepo pattern.
- `seed.rs` standalone — TMP-A4 is foundational invariant; deserves its own home.
- `main.rs` vs `lib.rs` split — standard Rust pattern; lets us write integration tests against the library API.

---

## 3. Dependency choices

**Versions are pinned once in the workspace root `Cargo.toml` `[workspace.dependencies]`; member crates inherit via `dep.workspace = true`.**

### tilemap-service direct dependencies

| Crate | Version | Reason |
|---|---|---|
| `loreweave_llm` | path = `../../sdks/rust/loreweave_llm` | LLM gateway client + wire-format mirrors. Service does NOT take a direct `reqwest` dep; HTTP lives in the SDK. |
| `tokio` | workspace (`^1.40` rt-multi-thread + macros + signal) | Async runtime; future HTTP server will need it. |
| `serde` + `serde_json` | workspace (`^1.0`) | JSON ser/de for TilemapView snapshot/roundtrip + smoke tests. |
| `blake3` | workspace (`^1.5`) | TMP-A4 deterministic seed (faster + cryptographic + 256-bit output vs sha256). |
| `thiserror` | workspace (`^1.0`) | Library error enums; pairs with `anyhow` at the binary boundary. |
| `anyhow` | workspace (`^1.0`) | Top-level error glue in `main.rs`. |
| `uuid` | workspace (`^1.10` serde + v4) | ChannelId composition + future PC/NPC id types. |
| `tracing` + `tracing-subscriber` | workspace (`^0.1` + `^0.3` env-filter) | Structured logging; matches Go services' zap-style. |

### loreweave_llm SDK direct dependencies (for reference; see [sdks/rust/loreweave_llm/Cargo.toml](../../sdks/rust/loreweave_llm/Cargo.toml))

| Crate | Reason |
|---|---|
| `reqwest` (rustls-tls + json + stream) | gateway HTTP. Workspace dep. |
| `serde` / `serde_json` | wire-format types. |
| `thiserror` | LlmError. |
| `uuid` | StreamRequest.model_ref + user_id query param. |
| `tokio` + `tracing` | async runtime + structured logging. |

**Dev dependencies:**

| Crate | Reason |
|---|---|
| `mockito` or `wiremock` | Phase 0b: mock the gateway endpoint for offline integration tests. Choose at Phase 0b. |

**Deliberately NOT chosen:**

| Not chosen | Why |
|---|---|
| `async-std` | tokio is the de-facto Rust async runtime; reqwest pins to tokio. |
| `hyper` direct | reqwest is sufficient for our use case; lower-level than needed. |
| `openapi-generator` | Adds build complexity; hand-roll Rust mirrors of the small StreamRequest + event-type surface (~150 lines manual vs generator overhead). |
| `sea-orm` / `sqlx` | No Postgres in Phase 0a/b. |
| `axum` / `actix-web` | No HTTP server surface in Phase 0a/b. Add when Phase 2 lights up. |
| `clap` | `main.rs` arg parsing is trivial in Phase 0a; defer until CLI grows. |

---

## 4. OpenAPI → Rust type mapping

Source: [contracts/api/llm-gateway/v1/openapi.yaml](../../contracts/api/llm-gateway/v1/openapi.yaml) (907 lines; we mirror only the StreamRequest + event surface for Phase 0a).

### StreamRequest (Rust mirror)

```rust
#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(rename_all = "snake_case")]
pub enum ModelSource {
    UserModel,
    PlatformModel,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(rename_all = "snake_case")]
pub enum StreamFormat {
    Openai,
    Anthropic,            // TMP_008b §3 prefers this for tool-use shape
    #[serde(rename = "vercel-ai-ui-v1")]
    VercelAiUiV1,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct StreamRequest {
    pub model_source: ModelSource,
    pub model_ref: uuid::Uuid,
    pub messages: Vec<serde_json::Value>,        // freeform per provider
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tools: Option<Vec<serde_json::Value>>,   // freeform per provider; tool-use payload
    pub temperature: f32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub max_tokens: Option<u32>,
    pub stream_format: StreamFormat,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub trace_id: Option<String>,
}
```

### Event types (Rust mirror; tagged enum)

```rust
#[derive(Debug, Deserialize, Clone)]
#[serde(tag = "event_type", rename_all = "snake_case")]
pub enum StreamEvent {
    Token { delta: String, /* … */ },
    Reasoning { delta: String, /* … */ },
    Usage { input_tokens: u32, output_tokens: u32, /* … */ },
    Done { finish_reason: String, /* … */ },
    Error { code: String, message: String, /* … */ },
}
```

Phase 0a writes type definitions only — actual SSE parsing deferred to Phase 0b.

### Endpoint constants

```rust
pub const GATEWAY_BASE_URL_DEFAULT: &str = "http://provider-registry-service:8085";
pub const INTERNAL_STREAM_PATH: &str = "/internal/llm/stream";
pub const PUBLIC_STREAM_PATH: &str = "/v1/llm/stream";
```

tilemap-service is service-to-service → `/internal/llm/stream` with internal-token auth (per gateway openapi.yaml).

---

## 5. Error strategy

Standard Rust hybrid:

- **Library errors** — `thiserror` enums per module (`types::Error`, `llm::Error`, `seed::Error`). Structured; callers can match.
- **Binary errors** — `anyhow::Result` in `main.rs`. Convenient `?` glue at the top.

```rust
// src/llm/errors.rs
#[derive(thiserror::Error, Debug)]
pub enum LlmError {
    #[error("gateway HTTP error: {0}")]
    Http(#[from] reqwest::Error),
    #[error("gateway returned error event: {code}: {message}")]
    GatewayErrorEvent { code: String, message: String },
    #[error("stream parsing failed: {0}")]
    StreamParse(String),
    #[error("validation rejected response after {attempts} attempts")]
    ValidationExhausted { attempts: u32 },
}
```

---

## 6. Provider abstraction sketch

The gateway abstracts providers — tilemap-service does NOT know whether the underlying call hits lmstudio, OpenAI, Anthropic, or any other provider. The provider is chosen via `model_ref: UUID` (registered in provider-registry).

```rust
// src/llm/client.rs — Phase 0a signature only
pub struct GatewayClient {
    base_url: String,
    internal_token: String,
    http: reqwest::Client,
}

impl GatewayClient {
    pub fn new(base_url: String, internal_token: String) -> Self { /* … */ }

    /// Phase 0a: signature only. Phase 0b implements SSE parsing.
    pub async fn stream(&self, request: StreamRequest) -> Result<StreamHandle, LlmError> {
        todo!("Phase 0b — SSE parser + per-object retry + canonical-default fallback")
    }
}

pub struct StreamHandle {
    // Phase 0b: futures::Stream<Item = StreamEvent>
}
```

**Phase 0b adds:** the actual SSE parsing loop, per-object retry per TMP_008b §5, canonical-default fallback per TMP_008b §6.

---

## 7. Determinism story

TMP-A4 axiom: `seed = blake3(reality_id || channel_id || template_id || seed_offset)` → byte-identical tilemap output across replays. Captured in `src/seed.rs`:

```rust
// src/seed.rs
use blake3::Hasher;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct TilemapSeed(pub u64);

pub fn derive_seed(
    reality_id: &str,
    channel_id: &str,
    template_id: &str,
    seed_offset: u64,
) -> TilemapSeed {
    let mut hasher = Hasher::new();
    hasher.update(reality_id.as_bytes());
    hasher.update(b"|");
    hasher.update(channel_id.as_bytes());
    hasher.update(b"|");
    hasher.update(template_id.as_bytes());
    hasher.update(b"|");
    hasher.update(&seed_offset.to_le_bytes());
    let hash = hasher.finalize();
    let bytes: [u8; 8] = hash.as_bytes()[..8].try_into().unwrap();
    TilemapSeed(u64::from_le_bytes(bytes))
}
```

Tested via smoke test: same inputs → same seed; different inputs → different seed.

---

## 8. Known limitations + deferred (Phase 0a)

Acknowledged upfront — documented in `README.md` user-facing:

1. **No real network call** — gateway client is signature-only. Phase 0b.
2. **No algorithm impl** — zone placer / modificator pipeline / Penrose tiling are stubs. Phase 1+.
3. **No DP-K1..K12 integration** — DP SDK is itself unbuilt. Mock at PoC boundary; Phase 2+ for real DP.
4. **No HTTP server** — tilemap-service is currently a binary that runs against fixtures. Phase 2+ for actual service mode.
5. **No Postgres** — Phase 2+.
6. **Anthropic `cache_control` not validatable** — the gateway does NOT expose Anthropic-specific prompt caching. TMP_008b §2 cacheable-prefix mechanic cannot be empirically tested through this stack. **Architectural finding** to feed back into TMP_008b at its next revision: the production tilemap-service must either (a) accept that Anthropic-specific cache savings are gateway-managed (opaque to caller) or (b) request a gateway extension that exposes provider-specific knobs to callers (heavyweight gateway change).
7. **Tools field is OpenAI-shaped per gateway contract — TMP_008b §3 Anthropic-shaped tool-use NOT directly transmittable** — surfaced during the `/review-impl` adversarial pass on 2026-05-14. Openapi `ChatStreamRequest.tools` is documented as "Optional. OpenAI-shaped tool definitions" (line 413-418). The `stream_format: anthropic` field controls the RESPONSE envelope, NOT the request body. Therefore TMP_008b §3's design — Anthropic-shaped `input_schema` + `tool_choice` forced — cannot be passed directly through the gateway. Production tilemap-service must construct OpenAI-shaped tool objects (`{"type": "function", "function": {...}}`) and the gateway translates internally for non-OpenAI providers. **Second architectural finding** to feed back into TMP_008b (alongside the cache_control gap from item 6). Action: TMP_008b §3 next revision should clarify whether the spec describes (a) the on-the-wire request to the gateway, (b) the on-the-wire request from the gateway to the provider after translation, or (c) a logical model contract that the tilemap-service translates from before sending. Best resolution path is (c) — TMP_008b §3 stays the logical contract; tilemap-service owns the OpenAI-shape translation as part of its gateway client.
8. **Direct lmstudio call NOT used** — per CLAUDE.md provider gateway invariant, all LLM calls go through the gateway. Even though the user asked for "lmstudio for cheaper cost", the architecturally-correct path is lmstudio registered as a `platform_model` in provider-registry-service; tilemap-service still calls the gateway. Phase 0b will document the registration step.

---

### 8.1 Phase 0b resolution (2026-05-15)

The two `/review-impl` architectural findings above are now addressed:

- **Item 7 (OpenAI-shaped tools / `tool_choice` not transmittable) — RESOLVED.**
  Phase 0b extended the gateway contract: `tool_choice` is now a
  `ChatStreamRequest` field and the canonical SSE envelope gained a streaming
  `tool_call` event (the gateway re-frames OpenAI `delta.tool_calls[]` /
  Anthropic `input_json_delta`). `tilemap-service classify` proved the path
  end-to-end against live lmstudio. Spec: `docs/specs/2026-05-15-tilemap-phase-0b-gateway-tooluse.md`.
- **New finding — LM Studio `tool_choice` is string-only.** LM Studio rejects
  the OpenAI object form `{"type":"function",...}`; only `none`/`auto`/`required`.
  TMP_008b §3.2's "force a specific tool" degrades to `"required"` + a
  single-tool array for the lmstudio path. Recorded in TMP_008b §12.8.
- **New finding — streaming usage needs `stream_options.include_usage`** (now
  set by the gateway) — without it OpenAI-compat providers omit token counts.
- **SDK fix — `loreweave_llm` streaming client must NOT set a total request
  `.timeout()`** (it aborts a healthy long stream); it uses `.read_timeout`
  (per-read idle) instead.
- **Item 6 (Anthropic `cache_control`) — still open**: the gateway exposes no
  provider-specific cache knob; unchanged by Phase 0b.

## 9. Phase 0a → 0b roadmap

| Phase | Scope | Estimated session count |
|---|---|---|
| **0a (this session)** | Scaffold + types + gateway client skeleton (no network) + smoke test + Dockerfile + README + this DESIGN.md | 1 session (~2-3 hrs) |
| **0b (next session)** | Real network call: SSE parser + 1 hardcoded L3 zone-classifier prompt → lmstudio (registered as platform_model in provider-registry) → measure tool-use forced-call success rate + token cost vs TMP_008b §12 estimates | 1 session (~3-4 hrs); REQUIRES provider-registry-service running locally + lmstudio model registration step documented in README |
| **1 (next-next session)** | Engine Stage 1: Fruchterman-Reingold zone placer (TMP_002) + 1-2 modificators (TMP_003). Determinism integration test: same seed → byte-identical zones. | 1-2 sessions |
| **2** | L3 zone classifier full retry loop (TMP_008b §5 per-object retry + §4 structured validation feedback + §6 canonical-default fallback). End-to-end small reality bootstrap. | 1-2 sessions |
| **3** | L4 regional narration + measurement findings doc back into TMP_008b. | 1 session |
| **4+** | DP integration, HTTP server surface, Forge AdminAction handlers, Postgres persistence. | Multi-session; out of PoC scope. |

---

## 10. Test layout (Phase 0a)

```
tests/
└── smoke.rs       — round-trip test: TilemapView struct → JSON → TilemapView; equality preserved
                     + seed determinism: same inputs → same TilemapSeed; different inputs → different
```

Phase 0b adds:
```
tests/
├── smoke.rs
└── gateway_mock.rs — wiremock-based gateway response mock; validates SSE parsing
```

Real network integration tests live in a separate `tests/integration_lmstudio.rs` that's `#[ignore]`d by default; run via `cargo test -- --ignored` when provider-registry + lmstudio are up.

---

## 11. Compliance check

Per CLAUDE.md repo rules:

| Rule | Phase 0a compliance |
|---|---|
| Contract-first | ✅ Mirrors `contracts/api/llm-gateway/v1/openapi.yaml`; no contract change. |
| Gateway invariant | ✅ All LLM calls route via `/internal/llm/stream`; no direct provider SDK calls. |
| Provider gateway invariant | ✅ Models picked via `model_ref: UUID`; tilemap-service does not know about lmstudio specifically. |
| Language rule | ⚠ **Rust is a NEW language for the monorepo** (Go + Python + TS so far). User-approved exception; aligns with TMP design intent ("clean-room Rust" per TMP_008b changelog). Future: tilemap-service may be the seed of a Rust SDK layer. |
| No hardcoded secrets | ✅ Internal token via env var `LOREWEAVE_INTERNAL_TOKEN`; gateway URL via env var or default constant; fail-fast if internal-token env var missing. |
| No hardcoded model names | ✅ `model_ref: UUID` from caller; resolved by provider-registry. |
| Each service owns its Postgres DB | ✅ N/A Phase 0a (no Postgres yet); Phase 4+ will own `tilemap_db`. |
| Frontend MVC rules | ✅ N/A (backend-only service). |

---

## 12. Open questions for user (DESIGN review)

None blocking. Decisions taken with reasonable defaults:

| Decision | Default chosen | Revisit trigger |
|---|---|---|
| Tokio runtime flavor (`current_thread` vs `multi_thread`) | `multi_thread` | If memory profile shows overhead unwanted. |
| Reqwest TLS backend (`rustls` vs `native-tls`) | `rustls` | If compatibility issue with internal infra. |
| `anyhow` at binary boundary vs `thiserror` end-to-end | hybrid | If we ever expose a public library API beyond the binary. |
| Cargo workspace vs standalone package | ~~**Standalone** for now (first Rust service)~~ → **Workspace at repo root** (post-`/review-impl` SDK extraction 2026-05-14). Members: `sdks/rust/loreweave_llm` + `services/tilemap-service`. Shared deps pinned in `[workspace.dependencies]`. | When 3rd Rust crate lands, decide whether to add a `[workspace.metadata]` description. |
| LLM gateway client location | ~~`services/tilemap-service/src/llm/`~~ → **`sdks/rust/loreweave_llm` workspace member** (post-`/review-impl` SDK extraction 2026-05-14). | — |
| Edition | `2024` (stable on rustc 1.85+; we have 1.89) | — |
