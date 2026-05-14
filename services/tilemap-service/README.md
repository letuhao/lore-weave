# tilemap-service

Procedural tilemap generation for LoreWeave non-cell channels (continent / country / district / town). First Rust microservice in the monorepo.

> **Status: Phase 0a scaffold (2026-05-14).** Compiling skeleton + types + LLM gateway client signatures only. **No actual network calls yet.** Phase 0b wires the real call. See [`DESIGN.md`](DESIGN.md) for the full roadmap.

---

## What this service does (eventually)

Per [TMP_001](../../docs/03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_001_tilemap_foundation.md) + [TMP_008b](../../docs/03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_008b_llm_contract_spec.md):

1. Owns 2 aggregates: `tilemap_view` (T2 / Channel scope, non-cell only — TMP-A1) + `tilemap_template` (T2 / Reality scope).
2. Generates a renderable tilemap per non-cell channel via a 4-layer pipeline: Skeleton (template) → Procedural placer (Fruchterman-Reingold zone graph + Penrose tiling + fractalize) → Modificators (terrain painter, road builder, treasure placer, etc.) → optional LLM augmentation (V2 L3 zone classifier + L4 regional narration; engine-only at V1+30d per AC-TMP-10).
3. Subscribes to MAP_001 `map_layout` deltas via DP-Ch24 to re-derive `child_cell_anchors` on author position edits (TMP-A6).
4. Handles 3 new Forge AdminAction sub-shapes: `Forge:RegenTilemap` (CosmeticOnly | FullRebootstrap), `Forge:EditTemplate`, `Forge:OverridePlacement` (V3 active; V1+30d schema-reserved).

## What this service does in Phase 0a (today)

- Compiles ✅
- Defines TMP_001 §2 core types in Rust (`ChannelTier`, `ZoneRole`, `PassageKind`, `TileState`, `TerrainKind`, `TilemapTemplate`, `TilemapView`, etc.) ✅
- Implements TMP-A4 deterministic seed helper using blake3 (`derive_seed`) with 6 unit tests + 4 smoke tests ✅
- Defines LLM gateway HTTP client **signature** mirroring [`contracts/api/llm-gateway/v1/openapi.yaml`](../../contracts/api/llm-gateway/v1/openapi.yaml) `StreamRequest` + `StreamEvent` shape ✅
- Returns `LlmError::NotImplementedPhase0a` from `GatewayClient::stream()` — the call site exists; actual SSE parsing lands at Phase 0b ⏸

## What this service does NOT do yet

| Capability | Phase | Why deferred |
|---|---|---|
| Real LLM call to gateway | 0b | Requires provider-registry-service running locally + lmstudio registered as a `platform_model` |
| Fruchterman-Reingold zone placer (TMP_002) | 1 | Non-trivial algorithm; needs its own session |
| Modificator pipeline (TMP_003) | 1 | Same |
| L3 per-object retry + canonical default fallback (TMP_008b §5-§6) | 2 | Needs Phase 0b foundation first |
| L4 regional narration + caching (TMP_008b §8) | 3 | After L3 lands |
| DP-K1..K12 SDK integration | 2+ | Rust DP SDK is itself unbuilt (only locked design) |
| HTTP server surface | 2+ | Currently a CLI binary |
| Postgres persistence | 4+ | In-memory only |
| Forge AdminAction handlers | 4+ | Needs HTTP server + DP write |
| Anthropic `cache_control` validation (TMP_008b §2) | **Cannot via this stack** | The LLM gateway does not expose Anthropic-specific prompt caching. Architectural finding to feed back into TMP_008b. |

## Quick start

### Prerequisites

- Rust 1.85+ (stable). Verify: `rustc --version`.
- Optional: Docker 20.10+ if you want to build the container.

### Build + test (Phase 0a)

```bash
cd services/tilemap-service
cargo build
cargo test
```

Expected: ~10 tests pass (4 smoke + 6 inline). Phase 0a does not exercise any network paths.

### Run the binary

```bash
LOREWEAVE_INTERNAL_TOKEN=dev_token cargo run --release
```

The Phase 0a binary just prints a tracing line documenting its own scope and exits. Phase 0b will add real CLI subcommands.

### Docker build

```bash
docker build -t loreweave/tilemap-service:0.1.0-phase0a \
  -f services/tilemap-service/Dockerfile \
  services/tilemap-service
```

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `LOREWEAVE_INTERNAL_TOKEN` | **Yes** (Phase 0b+) | (no default — service fails fast if missing per CLAUDE.md "no hardcoded secrets") | Bearer token for `/internal/llm/stream` |
| `LOREWEAVE_GATEWAY_URL` | No | `http://provider-registry-service:8085` | Base URL of the LLM gateway |
| `RUST_LOG` | No | `info,tilemap_service=debug` | `tracing-subscriber` env filter |

## Architecture compliance

| CLAUDE.md rule | Status | Notes |
|---|---|---|
| Contract-first | ✅ | Mirrors `contracts/api/llm-gateway/v1/openapi.yaml`; does not change the contract. |
| Gateway invariant | ✅ | All LLM calls route via `/internal/llm/stream`. |
| Provider gateway invariant | ✅ | Models picked via `model_ref: UUID`; the service never knows which provider answers. |
| Language rule | ⚠ **NEW** | Rust is a new language for the monorepo (Go + Python + TS before). User-approved exception aligning with TMP design intent. |
| No hardcoded secrets | ✅ | Internal token via env; service fails fast if missing. |
| No hardcoded model names | ✅ | `model_ref: UUID` from caller; provider-registry resolves. |
| Each service owns its DB | N/A | No Postgres in Phase 0a. |

## Phase roadmap

See [`DESIGN.md`](DESIGN.md) §9 for the full table. Quick summary:

- **0a (this commit)** — scaffold, types, gateway client signature, smoke test
- **0b** — real SSE parse + 1 L3 zone-classifier prompt → lmstudio via gateway; first cost + retry-rate measurements
- **1** — Fruchterman-Reingold zone placer + first 2 modificators + determinism integration test
- **2** — Full L3 retry loop (per-object retry + structured validation + canonical-default fallback)
- **3** — L4 regional narration + measurement findings doc back into TMP_008b
- **4+** — DP-K integration, HTTP server, Forge handlers, Postgres

## License

Same as parent repo (LoreWeave).
