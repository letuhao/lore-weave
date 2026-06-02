# Composition Service — V0 Implementation Plan

> **Date:** 2026-06-02 · **Phase:** PLAN · **Branch:** `feat/composition-service`
> **Design SSOT:** [composition-design.md](../specs/2026-06-02-composition-design.md) (§1 schema · §2 packer · §3 loop · §4 judge · §5 API · §6 sequences · §7+§11 benchmarks)
> **Requirements:** [composition-requirements.md](../specs/2026-06-02-composition-requirements.md) · **Vision:** [vision](../specs/2026-06-02-composition-service-vision.md)
> **Task size:** **XL** (new service, new DB, ≥10 files, side effects: DB + gateway + compose + contract). Plan file mandatory; `/amaw` recommended for M1 (schema/migrate) + M5 (authz/isolation).

---

## §0 Scope lock (what V0 ships)

V0 = **lore-grounded co-writer + visual planning**, single canonical timeline, co-writing/stream only.

**IN:** composition-service skeleton (FastAPI, own DB `loreweave_composition`) · §1 schema (incl. §11 fixes: `base_revision_id`, review-gated flywheel) · RAG packer (§2, 6 lenses + spoiler-cutoff + §11 A1/A2 isolation+spoiler-filter) · co-write stream loop (§3.1) · `judge_prose` advisory critic (§4) · `/v1/composition/*` API (§5) incl. prose-source proxy (decision B) · gateway proxy + compose wiring + DB-init · FE Composition tab filling the **stubbed AI panel** in the existing `ChapterEditorPage` (progressive disclosure: Classic=Casual, AI=Power).

**OUT (deferred — do NOT build):** autonomous loop (§3.2 → V1) · branches/takes/`scene_variant` (§8 → V1) · style/voice/reference profiles (§8.4 → V1) · consistency sweep (§8.6 → V1) · 同人/derivative (§9 → V2) · panel pop-out/multi-window engine (§8.5 → V1) · fact-provenance tiers (§11 OI-1 rich form → V1; V0 ships the review-gate only).

---

## §1 Service skeleton — file structure

Mirror `services/knowledge-service/` house style (single-DDL migrate, asyncpg pool, repo-per-table, httpx clients, JWT+internal middleware, no migration tool).

```
services/composition-service/
  Dockerfile                     # COPY sdks/python (context = repo root), like knowledge-service
  requirements.txt               # fastapi, uvicorn, asyncpg, pydantic[-settings], httpx, PyJWT,
  requirements-test.txt          #   prometheus-client, python-json-logger, loreweave_llm, loreweave_eval, tiktoken
  pytest.ini
  README.md
  app/
    __init__.py
    main.py                      # lifespan: create_pool → run_migrations → init clients → routers
    config.py                    # Settings (pydantic-settings): COMPOSITION_DB_URL, JWT_SECRET, INTERNAL_SERVICE_TOKEN,
                                 #   KNOWLEDGE_INTERNAL_URL, GLOSSARY_INTERNAL_URL, BOOK_INTERNAL_URL,
                                 #   LLM_GATEWAY_INTERNAL_URL, REDIS_URL, packer budget knobs
    deps.py                      # Depends() factories for repos + clients
    logging_config.py            # copy
    metrics.py                   # copy prometheus pattern
    middleware/
      jwt_auth.py                # copy — extracts user_id from JWT (user-scoped, 404 cross-user)
      internal_auth.py           # copy — INTERNAL_SERVICE_TOKEN guard for /internal/*
      trace_id.py                # copy
    db/
      pool.py                    # create_pool/close_pool/get_pool (single DB)
      migrate.py                 # the §1.2 DDL string (+ §11 base_revision_id) — idempotent
      models.py                  # Pydantic row models + StringConstraints length caps
      repositories/
        works.py                 # composition_work CRUD + resolve-by-book (§5 Work, §6.2)
        outline.py               # outline_node tree CRUD, LexoRank rank, If-Match version
        scene_links.py           # scene_link CRUD
        canon_rules.py           # canon_rule CRUD
        generation_jobs.py       # generation_job lifecycle + idempotency
        outbox.py                # outbox_events insert (txn-local)
    clients/
      knowledge_client.py        # context/build, timeline?before_order=, entities, relations, drawers/search
      glossary_client.py         # select-for-context, entities
      book_client.py             # chapter content read/write (prose-source canonical), revisions
      llm_client.py              # loreweave_llm SDK wrapper (stream chat + completion) — copy knowledge-service
      eval_client.py             # loreweave_eval JudgeLLMClient wrapper for judge_prose
    packer/
      __init__.py
      lenses.py                  # L0..L5 + L2′ gatherers (parallel, per-lens timeout, _safe_*)
      spoiler.py                 # §2.2 cutoff + §11-A2 semantic post-filter (drop hit if src order > story_order)
      budget.py                  # §2.3 priority ladder trim (tiktoken count)
      assemble.py                # §2.4 structured prompt blocks; §11-A1 isolation invariant asserted here
      pack.py                    # orchestrator: gather → cutoff/filter → budget → assemble → PackedContext
    engine/
      cowrite.py                 # §3.1 loop: retrieve → stream → (accept handled by FE) ; base_revision_id capture
      critic.py                  # §4 judge_prose: 4 dims + per-violation verdicts (advisory)
    routers/
      health.py · ping.py · metrics.py
      works.py                   # GET/POST /books/{id}/work · GET/PATCH /works/{pid}
      prose.py                   # GET/PUT /works/{pid}/chapters/{cid}/prose  (decision B proxy)
      outline.py                 # outline + scene-links endpoints
      canon.py                   # canon-rules + GET /templates
      engine.py                  # POST /generate (stream) · suggest-cast · jobs/{id} · critique · dismiss-violation · grounding
  tests/
    unit/                        # repos (mock pool), packer (cutoff/filter/budget pure-fn), critic prompt-shape
    integration/db/              # repo round-trips against a real test DB
```

Built-in `structure_template` rows (save_the_cat / hero_journey / story_circle / kishotenketsu / web_novel / generic) seeded idempotently in `migrate.py` (owner_user_id NULL).

---

## §2 Build order — milestones

Each milestone is independently VERIFY-able (tests green) before the next. TDD per BUILD rule.

| M | Title | Deliverable | Verify gate |
|---|---|---|---|
| **M0** | Skeleton boots | service dir, `main.py` lifespan, health/ping, config, Dockerfile, compose block, DB-init line, requirements | `docker compose up composition-service` → `GET /health` 200; pytest collects |
| **M1** | Schema + migrate ⚠️`/amaw` | §1.2 DDL (incl. `base_revision_id`) + template seed; `models.py`; idempotent re-run | migrate runs twice clean; integration DB test inserts each table |
| **M2** | Repos + Work resolution | `works/outline/scene_links/canon_rules/generation_jobs/outbox` repos; resolve-prefers-marked (§6.2); If-Match version bump | unit (mock) + integration round-trips; resolve returns found/none/candidates |
| **M3** | Clients + prose-source | knowledge/glossary/book/llm/eval client wrappers; `prose.py` GET/PUT proxy to book-service (+revisions, base_revision_id on read) | unit with httpx mock; live-smoke: prose GET proxies a real chapter |
| **M4** | Packer | `packer/*` — lenses, spoiler cutoff, **§11-A2 semantic filter**, **§11-A1 isolation**, budget ladder, assemble; `GET …/grounding` preview | unit: cutoff drops future events; A2 drops over-order semantic hits; A1 asserts project-scoped reads; budget trims lowest-first |
| **M5** | Isolation/authz hardening ⚠️`/amaw` | every read project_id+user_id scoped; cross-user → 404; canonical reads only (no branch leak, future-proof) | unit: cross-user work → 404; packer never issues unscoped search (assert in test) |
| **M6** | Co-write engine + critic | `engine/cowrite.py` stream via llm SDK; `engine/critic.py` judge_prose advisory; `POST /generate` (budget pre-check → stream → job_id), `/critique`, `/dismiss-violation`, `/suggest-cast` | unit: budget pre-check blocks over-cap; critic returns 4 dims + violations[]; **live-smoke: real /generate stream end-to-end on stack-up** |
| **M7** | Contract + gateway | `contracts/api/composition/v1/openapi.yaml` (additive); gateway `compositionProxy` (`/v1/composition`, `selfHandleResponse:false` for SSE) + env wiring `COMPOSITION_URL` | gateway routes `/v1/composition/*`; SSE passes through |
| **M8** | FE Composition tab (Power panel) | fill stubbed AI panel in `ChapterEditorPage`: `features/composition/` (api.ts/types.ts/hooks/context/components) — Grounding panel, Canon rules, co-write compose-bar+stream, inline critic flags; Casual=Classic untouched | vitest unit (hooks/components); Playwright smoke with test account: open Composition tab, generate a scene, see grounding + critic flag |
| **M9** | Review-gated flywheel wiring (§11 OI-1) | extraction trigger fires on chapter **review-state** (`status=done`/AI-marks cleared), not bare accept; outbox event `composition.scene_committed` | unit: accept alone does NOT emit canonization; review does |

**Critical-path order:** M0→M1→M2→M3→M4→M6 is the backend spine. M5 folds into M2/M4 (do not skip — load-bearing per memory). M7 unblocks M8. M9 closes the flywheel loop.

---

## §3 §11 fixes → where they land

| Fix | Milestone | Implementation |
|---|---|---|
| **OI-1** review-gated canonization | M9 (+M6 accept) | extraction-trigger outbox event emitted on `outline_node.status='done'` transition / AI-mark-clear, not on `/generate` accept |
| **OI-2** accept-staleness | M3 (read) + M6 (accept) | `generation_job.base_revision_id` set at draft time; prose-source PUT uses If-Match on book-chapter revision; mismatch → 409 conflict surface; ghost tokens FE-local until accept |
| **A1** isolation invariant | M4 + M5 | every lens read carries `project_id`+`user_id`; `packer/assemble.py` asserts no unscoped call; canonical mode only (no branch table in V0) |
| **A2** semantic spoiler-filter | M4 | `packer/spoiler.py` post-filters L4/L5 hits by source `chronological_order ≤ story_order`; missing-position → conservative drop + log |

---

## §4 Integration touch-points (additive only — no other service changed)

1. **`infra/postgres-init/01-databases.sql`** — add `loreweave_composition` CREATE line.
2. **`infra/docker-compose.yml`** — new `composition-service` block (copy knowledge-service: build context `..`, env `COMPOSITION_DB_URL`/`JWT_SECRET`/`INTERNAL_SERVICE_TOKEN`/`*_INTERNAL_URL`/`LLM_GATEWAY_INTERNAL_URL`/`REDIS_URL`, healthcheck, port e.g. `8217:8093`); add `COMPOSITION_URL` to api-gateway-bff env + `depends_on`.
3. **`services/api-gateway-bff/src/gateway-setup.ts`** — add `compositionProxy` (pathFilter `/v1/composition`, `selfHandleResponse:false`, 503-on-down handler like knowledgeProxy) + `instance.use` branch + URL param.
4. **`contracts/api/composition/v1/openapi.yaml`** — new (contract-first, frozen before M8 FE).
5. **`worker-infra` outbox relay** — `aggregate_type='composition'` → `loreweave:events:composition` (config-only; relay is generic). knowledge-service already consumes `chapter.saved` for the flywheel — **verify** its existing handler covers composition-committed chapters (book-service emits chapter.saved regardless of author), so M9 may need NO knowledge-service change. Confirm at M9.

**No edits to** knowledge/glossary/book service code — all reuse via existing HTTP (COMP-A6). If a needed read isn't exposed, STOP and reclassify (don't silently add an endpoint to another service).

---

## §5 Test strategy

- **Unit** (mock pool/httpx): repos, packer pure-functions (cutoff/A2-filter/budget ladder), critic prompt-shape, Work-resolution branches, budget pre-check. i18n FE mock = key-passthrough (memory).
- **Integration/db**: repo round-trips on a real `loreweave_composition_test` DB; If-Match 412 path; resolve found/none/candidates.
- **Live-smoke (cross-service, §VERIFY gate)** — touches ≥4 services (composition+knowledge+glossary+book+gateway+llm). Required token at VERIFY: `live smoke: /generate streamed a grounded scene end-to-end` OR `LIVE-SMOKE deferred to D-COMP-V0-LIVE-SMOKE` (needs BYOK LLM key in provider-registry; laptop has no LM Studio). Decide at M6.
- **FE**: vitest (hooks own logic, components render-only per MVC rule); Playwright smoke with `claude-test@loreweave.dev`.

---

## §6 Risks / watch-items

- **SceneAnchor ↔ outline sync** (§7 design risk, D1=b) — V0 reads scene order from anchor order in content; metadata via If-Match. Build with care + concurrent-edit tests (ties to OI-2/OI-3).
- **LLM key dependency** — `/generate` + `judge_prose` need a real provider; laptop blocker → live-smoke likely deferred to D-COMP-V0-LIVE-SMOKE with unit/mock coverage meanwhile.
- **Packer hit-position metadata (A2)** — depends on `drawers/search` returning source chronological position per hit. If absent → conservative-drop fallback + note a follow-up to enrich the hit shape (can't change knowledge per A6; may need the position to be derivable from returned chunk/chapter id).
- **Port assignment** — pick a free host port (knowledge=8216, next free e.g. 8217); container port e.g. 8093.

---

## §7 Definition of done (V0)

- All 9 milestones VERIFY-green; backend unit+integration pass; FE vitest pass; Playwright smoke opens the Composition tab and co-writes one grounded scene with a visible critic flag.
- Live-smoke run OR explicitly deferred (D-COMP-V0-LIVE-SMOKE) with reason.
- Contract committed before FE; gateway routes; compose+db-init wired.
- §11 fixes verifiably present (4 targeted tests).
- SESSION_HANDOFF updated; clean commits per milestone.
