# Cycle 3: API contract freeze

> Contract-first cycle. Freeze the `lore-enrichment-service` OpenAPI surface +
> stub handlers BEFORE any frontend flow or business logic. Stubs return shapes,
> not behaviour. brief-structure-validator.sh asserts all 10 sections + ≤4000
> tokens + ≥3 🔴 lines in REMINDERS.

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Author `contracts/api/lore-enrichment/` OpenAPI 3.1 spec covering the four resource families — **jobs**, **proposals**, **sources** (corpora), **templates** — plus the H0 author **promote** endpoint. Wire stub FastAPI handlers in `lore-enrichment-service` that validate against the spec and return placeholder shapes (200) or `501 Not Implemented` for actions not yet built. This is a contract freeze: shapes are load-bearing, behaviour is not.
- **Acceptance gate:** `scripts/raid/verify-cycle-3.sh` exits 0 (created by this cycle's runner — forward ref OK).
- **Top 3 LOCKED decisions consumed:** H0 (enriched≠canon + promote lifecycle), Q1 (proposal store mirrors `pending_facts`), Q-R1 (separate service, own DB).
- **DPS count:** 2 (low-DPS posture per locked cost decision).
- **Estimated wall time:** 2–4 h.

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C0
- Files expected to exist (grep-able paths): `services/lore-enrichment-service/app/main.py` (FastAPI skeleton + `/health`), `services/lore-enrichment-service/app/config.py` (fail-fast secrets), `services/lore-enrichment-service/app/deps.py`, gateway route `/v1/lore-enrichment/*` wired in C0.

## Scope (IN)
- `contracts/api/lore-enrichment/openapi.yaml` (OpenAPI 3.1), following sibling-service layout under `contracts/api/`. Resource families + endpoints:
  - **jobs** — `POST /v1/lore-enrichment/jobs` (create/estimate), `GET .../jobs`, `GET .../jobs/{job_id}`, lifecycle actions `POST .../jobs/{job_id}/{start|pause|resume|cancel}`.
  - **proposals** — `GET .../proposals`, `GET .../proposals/{id}`, review actions `POST .../proposals/{id}/{approve|reject|edit}`, and the H0 **`POST .../proposals/{id}/promote`** (author-only canonization).
  - **sources** — `GET/POST .../sources` (corpus registration metadata only; no ingest logic here).
  - **templates** — `GET/POST .../templates` (enrichment template CRUD shape).
- Schemas: `EnrichmentJob`, `EnrichmentProposal`, `SourceCorpus`, `EnrichmentTemplate`, plus error envelope. Proposal schema MUST expose H0 fields: `origin`, `technique`, `provenance_json`, `confidence`, `source_refs_json`, `cultural_grounding_ref`, `review_status` (enum `proposed|author_reviewing|approved|promoted|rejected`), and on promote-result `promoted_entity_id|promoted_by|promoted_at|original_technique`.
- Stub handlers under `services/lore-enrichment-service/app/api/` (routers per family) wired into the existing FastAPI app, returning spec-valid placeholder bodies (`200`) or `501` for unimplemented actions. Per-user/per-project scope params (`book_id`/`project_id`, `user_id` from auth) present in signatures (Q3).
- A spec-lint invocation + a route-presence check folded into `scripts/raid/verify-cycle-3.sh`.
- Update `docs/sessions/SESSION_PATCH.md` (SESSION phase).

## Scope (OUT — explicitly)
- NO business logic: no real gap detection, no LLM calls, no embedding/retrieval, no DB writes, no glossary/KG write-back. Those are C7–C14.
- NO migrations / schema DDL — that is C2. Reference column names only in the contract; do not create tables.
- NO model names in code or spec examples (resolved via provider-registry; do not hardcode `qwen`/`bge-m3`).
- NO edits to `world-service`, `game-server`, `tilemap`, `infra/existing-prod/`, glossary-service, knowledge-service, or the climate/geo eval files.
- NO frontend flow — contract-first means FE waits for this freeze.
- NO new RAG/langchain/llamaindex deps.

## Acceptance criteria (CI gates — exit code 0 = pass)
- Lints pass: OpenAPI spec lints clean (`openapi-spec-validator` or `redocly lint` on `contracts/api/lore-enrichment/openapi.yaml`); FastAPI app imports without error (`python -c "import app.main"`).
- Tests pass: route-presence test asserts every spec path is mounted; promote endpoint exists and is reachable; stub routes return **200 or 501** (no 404/500) for happy-path requests.
- Integration smoke: app boots (`uvicorn` import-mode); `GET /v1/lore-enrichment/proposals` returns 200 with spec-valid empty list; `POST .../proposals/{id}/promote` returns 200/501 with the H0 origin-marker shape.
- `scripts/raid/verify-cycle-3.sh` exits 0 (spec lint + route presence + stub-status checks).
- This cycle is single-service (lore-enrichment-service only) → **no live-smoke token required**.

## DPS parallelism plan
- **DPS 1 — Contract author:** writes `contracts/api/lore-enrichment/openapi.yaml` (all 4 families + promote + schemas + error envelope). Worktree files: `contracts/api/lore-enrichment/`. (return budget: 1500 tokens summary)
- **DPS 2 — Stub wiring:** implements routers under `services/lore-enrichment-service/app/api/` against the frozen spec + `scripts/raid/verify-cycle-3.sh` + route-presence test. Worktree files: `services/lore-enrichment-service/app/`, `scripts/raid/verify-cycle-3.sh`. Consumes DPS 1's spec; sequence DPS 1 → DPS 2 (spec freeze precedes stubs).

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **H0 leak in the contract:** does the proposal schema make enriched content structurally distinct (required `origin`, `review_status`, `confidence<1.0`, `pending_validation`)? Is there ANY default path where a proposal could be represented as canon without an explicit `promote`? Promote MUST be a distinct endpoint, not a `review_status` PATCH.
- **Promote authorization shape:** is `promote` scoped so only the book/project owner ("author") can call it (Q3 + locked promotion-authority)? Even as a stub, the signature must carry the principal — not anonymous.
- **Hardcoded model names:** grep the spec examples + stub code for `qwen`, `bge`, `gpt`, `llama`, endpoint URLs — none allowed (provider-registry resolves these).
- **Stub false-green:** do stubs return real spec-valid shapes, or empty `{}` that would pass a lint but break the FE contract? `501` must be used for genuinely-unimplemented actions, not as a catch-all to dodge shape work.
- **Scope creep:** any DB write, migration, LLM/embedding call, or glossary/KG touch is OUT — flag it.
- **Spec/stub drift:** every spec path mounted; every mounted route in the spec. No orphan routes.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All 4 resource families + `promote` endpoint present in spec AND mounted as stubs.
- Proposal schema carries all H0 fields incl. permanent origin marker.
- No OUT items touched (no migrations, no logic, no other services, no eval files, no FE).
- `scripts/raid/verify-cycle-3.sh` exits 0 (spec lints; stub routes 200/501).
- No hardcoded model names. Single-service → no live-smoke needed.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle decomposition (C3 row + parallelism notes): [CYCLE_DECOMPOSITION.md](../../plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md)
- LOCKED decisions (full list — H0, Q1–Q6, Q-R1/R2, execution/tooling): [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-05-30-lore-enrichment/OPEN_QUESTIONS_LOCKED.md)
- Plan + ground truth: [PLAN.md](../../03_planning/lore-enrichment/PLAN.md) · [CLARIFY_GROUND_TRUTH.md](../../03_planning/lore-enrichment/CLARIFY_GROUND_TRUTH.md)
- LOCKED decisions consumed (full list): H0, Q1, Q3, Q-R1, Q-R2, plus execution decision (no hardcoded model names) and isolation decision.

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **H0 (CORE):** enriched ≠ canon. Proposal schema MUST be structurally distinct (`origin`, `review_status` proposed→author_reviewing→approved→promoted|rejected, `confidence<1.0`, quarantine). Promote is a DEDICATED endpoint and the ONLY path to canon; promoted result retains the permanent origin marker (`promoted_from_proposal_id/by/at`, `original_technique`).
- 🔴 **Q1 + Q-R1:** proposal store mirrors knowledge-service `pending_facts` (confirm/reject + injection-defense + confidence/quarantine); this is the separate `lore-enrichment-service` — own surface, own DB.
- 🔴 **No hardcoded model names / URLs:** spec examples and stub code resolve LLM + embedding via provider-registry. Grep before completing.
- 🔴 **Acceptance MUST include:** `scripts/raid/verify-cycle-3.sh` exits 0 — spec LINTS clean AND every stub route returns 200/501 (never 404/500); promote endpoint present and reachable.
- 🔴 **Do NOT touch:** no migrations (C2), no logic/LLM/embedding/glossary/KG writes, no other services, no eval files, no FE flow. Contract freeze ONLY.
- 🔴 **Fresh session reminder:** this is a new `/raid 3` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + OPEN_QUESTIONS_LOCKED.md ONLY.
