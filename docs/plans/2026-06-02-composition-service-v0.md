# Composition Service — V0 Implementation Plan

> **Track:** LOOM · **Date:** 2026-06-02 · **Phase:** PLAN · **Branch:** `feat/composition-service`
> **Design SSOT:** [composition-design.md](../specs/2026-06-02-composition-design.md) (§1 schema · §2 packer · §3 loop · §4 judge · §5 API · §6 sequences · §7+§11 benchmarks)
> **Requirements:** [composition-requirements.md](../specs/2026-06-02-composition-requirements.md) · **Vision:** [vision](../specs/2026-06-02-composition-service-vision.md)
> **Task size:** **XL** (new service, new DB, ≥10 files, side effects: DB + gateway + compose + contract + **one knowledge-service ingest line, §4.6**). Plan file mandatory; `/amaw` recommended for M1 (schema/migrate) + M5 (authz/isolation).
> **⚠️ Updated 2026-06-03 after an architecture review** (design [§12](../specs/2026-06-02-composition-design.md#§12)) that ported lore-enrichment's hard-won bug-classes + contract-verified the knowledge-service surfaces. Net changes: lenses re-spec'd (L1b timeline + L4 spoiler-filtered; **L5 deferred**); **dual-axis spoiler-cutoff**; **`BookProfile`/de-bias from M0**; judge ≠ drafter; real token metering; tolerant critic parse. Boundary: composition + additive infra; **lore-enrichment never touched.**
> **⚠️⚠️ PREREQUISITE — Canon Model Cycle 0** ([canon-model spec](../specs/2026-06-03-canon-model.md)). A deeper /review-impl found OI-1 (accept canonizes — no draft/published gate) and the spoiler cutoff (`chronological_order` never written → no-op) were **platform-level, unfixable from composition**. PO decision: solve durably as platform primitives FIRST. **Composition depends on Canon Model CM1–CM4** (editorial lifecycle · canon=published · dual-order populated · provenance). The old standalone `chapter_index` fix (Mk) is absorbed into Canon Model CM4. Build Canon Model (its own spec/plan, `/amaw`) → THEN composition M0.

---

## §0 Scope lock (what V0 ships)

V0 = **lore-grounded co-writer + visual planning**, single canonical timeline, co-writing/stream only.

**IN:** composition-service skeleton (FastAPI, own DB `loreweave_composition`) · §1 schema (incl. §11 fixes: `base_revision_id`, review-gated flywheel) · RAG packer (§2 — lenses **re-spec'd per §12 contract-check**: L0 · L1a state · **L1b timeline (the in-world spoiler-safe lens)** · L2/L2′ · L3 · L4 reading-order-filtered semantic · **L5 DEFERRED**; §11 A1/A2 isolation + two-axis spoiler-cutoff) · **`BookProfile`/`source_language` threading from M0 (de-bias, §2.6)** · co-write stream loop (§3.1, real token metering) · `judge_prose` advisory critic (§4 — distinct model from drafter; tolerant parse) · `/v1/composition/*` API (§5) incl. prose-source proxy (decision B) · gateway proxy + compose wiring + DB-init · **consumes the Canon Model Cycle-0 primitives (§4.6 — built first, separate cycle): accept→draft, review→publish→canon (OI-1 structural), dual-order spoiler-filter** · FE Composition tab filling the **stubbed AI panel** in the existing `ChapterEditorPage` (progressive disclosure: Classic=Casual, AI=Power).

**OUT (deferred — do NOT build):** autonomous loop (§3.2 → V1) · branches/takes/`scene_variant` (§8 → V1) · style/voice/reference profiles (§8.4 → V1) · consistency sweep (§8.6 → V1) · 同人/derivative (§9 → V2) · panel pop-out/multi-window engine (§8.5 → V1) · fact-provenance tiers (§11 OI-1 rich form → V1; V0 ships the review-gate only) · **L5 long-term-summary lens (no HTTP read endpoint exists → needs a separate knowledge-service surface, §12.1)** · **V1 judge-diversity hard gate (V0 critic is advisory/single-model-distinct; ≥2-family+κ gate lands when the autonomous loop does)**.

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
      profile.py                 # §2.6 BookProfile + NEUTRAL default + get_book_profile (missing row → NEUTRAL); source_language resolve via book-service
      lenses.py                  # L0/L1a/L1b-timeline/L2/L2′/L3/L4 gatherers (L5 deferred) — parallel, per-lens timeout, _safe_*
      spoiler.py                 # §2.2 TWO-axis: L1b in-world (before_chronological) + L4 reading-order (resolve source_id→book sort_order); conservative-drop + LOG l4_dropped_no_position
      budget.py                  # §2.3 priority ladder trim (tiktoken count)
      assemble.py                # §2.4 structured prompt blocks; §11-A1 chokepoint assert (project_id non-null on every lens); profile threaded into wrapper
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
| **M3** | Clients + prose-source | knowledge/glossary/book/llm/eval client wrappers; `prose.py` GET/PUT proxy to book-service `chapter_drafts`+`chapter_revisions` (base_revision_id on read); **PUT echoes a MANDATORY `expected_draft_version`** (§13 PS2 — body field, not If-Match) → 409 conflict surface; **PUT writes the DRAFT (no canonization); a separate `/publish` proxy (CM1) is the canon-affecting call** (OI-1 structural); **ownership chokepoint: verify JWT user owns book_id BEFORE any internal glossary/knowledge read (§13 SEC2)** | unit with httpx mock; **unit: PUT without expected_draft_version is rejected client-side; 409 maps to conflict**; **unit: cross-user book → 404 before internal call**; live-smoke: prose GET proxies a real chapter |
| **CM0** | **Canon Model prerequisite** (separate Cycle 0 — [spec](../specs/2026-06-03-canon-model.md) · [plan](2026-06-03-canon-model-cycle0.md)) | CM1 editorial_status + `/publish` + `chapter.published` · CM2 relay · CM3 knowledge extract-on-publish (pinned revision) · CM4 dual-order populated (`event_order` from sort_order + `chronological_order` from `event_date_iso`) + passage `chapter_index` | **Cycle 0 VERIFY-green BEFORE composition M0.** Composition M3/M4/M6/M9 consume CM1–CM4. Absorbs the old Mk. |
| **M4** | Packer (lenses re-spec'd §2.1) | `packer/*` — L0/L1a/**L1b timeline**/L2/L2′/L3/**L4 reading-order-filtered** (L5 deferred); **two-axis spoiler-cutoff §2.2**; **§11-A1 chokepoint assertion**; budget ladder; assemble; **`BookProfile` read at pack-time (NEUTRAL default)**; `GET …/grounding` preview | unit: **L1b drops future in-world events** (`before_chronological`); **L4 drops hits from at/after the scene's chapter + LOGs `l4_dropped_no_position`** (no silent dead-filter); A1 test asserts `project_id` non-null on every lens call; budget trims lowest-first; NEUTRAL profile when no row; **cache GLOSSARY entity_id (stable), not knowledge canonical_id (rename-sensitive); soft-absent id skipped not crashed (§13 DI3)**; **"no knowledge project for book" → grounding-unavailable signal, not silent-thin (§13 C3a)** |
| **M5** | Isolation/authz hardening ⚠️`/amaw` | every read project_id+user_id scoped; cross-user → 404; canonical reads only (no branch leak, future-proof); **assert no lens omits `project_id`** (timeline/entities widen to all-projects otherwise, §12.1) | unit: cross-user work → 404; packer never issues unscoped/no-project search (assert in test) |
| **M6** | Co-write engine + critic | `engine/cowrite.py` stream via llm SDK (**real usage-frame metering, absent/zero→over-estimate**); `engine/critic.py` judge_prose advisory (**distinct model from drafter; tolerant `violations[]` parse**); `BookProfile`/`source_language` threaded into draft + judge prompts; `POST /generate` (budget pre-check → stream → job_id), `/critique`, `/dismiss-violation`, `/suggest-cast` | unit: budget pre-check blocks over-cap + meters real tokens (not 0 on empty frame); critic returns 4 dims + violations[]; **malformed verdict filtered not batch-rejected**; CJK/non-English prompt has no English-only illustrative phrases; **`<lore>`+`<guide>` sanitized before assembly (§13 SEC3)**; **2nd /generate cancels in-flight job + idempotency_key (§13 S2)**; **critique re-resolves ACTIVE canon rules, deleted rule not enforced (§13 CC2)**; critic timeout/402 degrades, never blocks accept; **live-smoke: real /generate stream end-to-end on stack-up** |
| **M7** | Contract + gateway | `contracts/api/composition/v1/openapi.yaml` (additive); gateway `compositionProxy` (`/v1/composition`, `selfHandleResponse:false` for SSE) + env wiring `COMPOSITION_URL` | gateway routes `/v1/composition/*`; SSE passes through |
| **M8** | FE Composition tab (Power panel) | fill stubbed AI panel in `ChapterEditorPage`: `features/composition/` (api.ts/types.ts/hooks/context/components) — Grounding panel, Canon rules, co-write compose-bar+stream, inline critic flags; **client-side DEBOUNCED autosave that NEVER autosaves ghost tokens (§13 SC4 — no server autosave exists; each save = revision + extraction event)**; Casual=Classic untouched | vitest unit (hooks/components); **ghost tokens excluded from autosave until accept**; Playwright smoke with test account: open Composition tab, generate a scene, see grounding + critic flag |
| **M9** | OI-1 via Canon Model publish (structural, chapter-gate) | OI-1 is a DATA-MODEL invariant from CM0: composition **accept → writes `draft` chapter** (no canonization); **review/done → `/publish` → `chapter.published` → extraction** (CM3). **Chapter-gate (sweep): `/publish` enabled ONLY when ALL the chapter's scenes are `status='done'`** (no unreviewed scene canonized). composition emits `composition.scene_committed` telemetry. Grounding needs a `knowledge_projects` row (verified skip otherwise). | unit: accept writes draft, does NOT publish; **publish blocked while any scene ≠ done**; all-done → `/publish`; live: publish → extraction on pinned revision (CM3); no-project skip documented |

**Critical-path order:** **CM0 (Canon Model Cycle 0) → ** M0→M1→M2→M3→M4→M6 is the backend spine. CM0 is a SEPARATE prerequisite cycle (own spec/plan) that must be VERIFY-green first — M4's dual-order spoiler-filter + M9's OI-1 + M3's accept→draft/publish all consume it. M5 folds into M2/M4 (do not skip — load-bearing per memory). M7 unblocks M8. M9 closes the flywheel loop. **BookProfile/de-bias threading (§2.6) spans M4 (pack-time read) + M6 (prompt threading) — not a separate milestone, but verify it at both.**

---

## §3 §11 fixes → where they land

| Fix | Milestone | Implementation |
|---|---|---|
| **OI-1** review-gated canonization | M9 (+M6 accept) | extraction-trigger outbox event emitted on `outline_node.status='done'` transition / AI-mark-clear, not on `/generate` accept |
| **OI-2** accept-staleness | M3 (read) + M6 (accept) | `generation_job.base_revision_id` set at draft time; prose-source PUT uses If-Match on book-chapter revision; mismatch → 409 conflict surface; ghost tokens FE-local until accept |
| **A1** isolation invariant | M4 + M5 | every lens read carries `project_id`+`user_id`; `packer/assemble.py` asserts `project_id` **non-null** on every call (timeline/entities widen to all-projects otherwise, §12.1); canonical mode only (no branch table in V0) |
| **A2** spoiler-filter (Canon Model) | **CM0** + M4 | **Both axes populated by Canon Model CM4** (`event_order`/reading_order from sort_order; `chronological_order` from `event_date_iso`). `packer/spoiler.py` filters L1b events + L4 passages by the populated order ≤ scene cutoff; missing chronological_order → fall back to reading_order; **LOG drops** (no silent dead-filter). Relations (L1a) = currently-valid only. |

---

## §4 Integration touch-points (additive — plus ONE knowledge-service ingest fix, see #6)

1. **`infra/postgres-init/01-databases.sql`** — add `loreweave_composition` CREATE line.
2. **`infra/docker-compose.yml`** — new `composition-service` block (copy knowledge-service: build context `..`, env `COMPOSITION_DB_URL`/`JWT_SECRET`/`INTERNAL_SERVICE_TOKEN`/`*_INTERNAL_URL`/`LLM_GATEWAY_INTERNAL_URL`/`REDIS_URL`, healthcheck, port e.g. `8217:8093`); add `COMPOSITION_URL` to api-gateway-bff env + `depends_on`. **Build BOTH composition-service AND its worker image** (separate tags, enrichment F-LIVE-1 lesson) via `scripts/build-stack.sh`.
3. **`services/api-gateway-bff/src/gateway-setup.ts`** — add `compositionProxy` (pathFilter `/v1/composition`, `selfHandleResponse:false`, 503-on-down handler like knowledgeProxy) + `instance.use` branch + URL param.
4. **`contracts/api/composition/v1/openapi.yaml`** — new (contract-first, frozen before M8 FE).
5. **`worker-infra` outbox relay** — `aggregate_type='composition'` → `loreweave:events:composition` (config-only; relay is generic). knowledge-service already consumes `chapter.saved` for the flywheel — **verify** its existing handler covers composition-committed chapters (book-service emits chapter.saved regardless of author), so M9 may need NO knowledge-service change. Confirm at M9.
6. **⚠️ Canon Model prerequisite (Cycle 0) — the cross-service changes live THERE, not here** ([canon-model spec](../specs/2026-06-03-canon-model.md)). CM1 book-service (`editorial_status` + `published_revision_id` + `/publish` + `chapter.published`) · CM2 worker-infra relay · CM3 knowledge extract-on-publish · CM4 dual-order + passage `chapter_index` (absorbs the old standalone fix). Composition only **consumes** these. The Canon Model has its own plan + `/amaw` (schema/migration + cross-service contract). **Boundary unchanged for lore-enrichment: never touched.**

**Composition itself adds no edits to** glossary/book/knowledge service code — reuse via existing HTTP + the Canon Model primitives (COMP-A6). For any OTHER missing read, STOP and reclassify (don't silently add an endpoint). **L5 summaries are NOT exposed over HTTP** → L5 deferred (a future, separate knowledge-service touch-point — out of V0 scope).

---

## §5 Test strategy

- **Unit** (mock pool/httpx): repos, packer pure-functions (L1b in-world cutoff/L4 reading-order-filter+`l4_dropped_no_position` log/budget ladder), **BookProfile NEUTRAL-default on missing row + source_language thread**, **A1 chokepoint (`project_id` non-null) assertion**, critic prompt-shape (**no English-only illustrative phrase + tolerant `violations[]` parse** drops a malformed item without batch-reject), **token-metering fallback (empty/zero usage frame → over-estimate, clamp ≥0)**, Work-resolution branches, budget pre-check. i18n FE mock = key-passthrough (memory).
- **Integration/db**: repo round-trips on a real `loreweave_composition_test` DB; If-Match 412 path; resolve found/none/candidates.
- **Live-smoke (cross-service, §VERIFY gate)** — touches ≥4 services (composition+knowledge+glossary+book+gateway+llm). Required token at VERIFY: `live smoke: /generate streamed a grounded scene end-to-end` OR `LIVE-SMOKE deferred to D-COMP-V0-LIVE-SMOKE` (needs BYOK LLM key in provider-registry; laptop has no LM Studio). Decide at M6.
- **FE**: vitest (hooks own logic, components render-only per MVC rule); Playwright smoke with `claude-test@loreweave.dev`.

---

## §6 Risks / watch-items

- **SceneAnchor ↔ outline sync** (§7 design risk, D1=b) — V0 reads scene order from anchor order in content; metadata via If-Match. Build with care + concurrent-edit tests (ties to OI-2/OI-3).
- **LLM key dependency** — `/generate` + `judge_prose` need a real provider; laptop blocker → live-smoke likely deferred to D-COMP-V0-LIVE-SMOKE with unit/mock coverage meanwhile.
- **Packer hit-position / spoiler axis — RESOLVED via Canon Model (§12.4).** Verified: `chronological_order`/`event_order` are NEVER written (no-op filter) and `chapter_index` is `None` on ingest. Fix = **Canon Model CM4** populates BOTH axes (reading_order from sort_order; chronological_order from `event_date_iso`). True in-world flashback-safety becomes real (bounded by `event_date_iso` quality), not a V0 residual. Composition consumes it.
- **De-bias / language bias (§2.6) — HIGH, baked in not deferred.** Composition generates prose; an English-biased draft/judge prompt drifts a CJK/VN book to English (enrichment paid 3 cycles for this). Thread `BookProfile`/`source_language` from M0; ban English-only illustrative phrases in prompts; verify at M4 + M6.
- **Port assignment** — pick a free host port (knowledge=8216, next free e.g. 8217); container port e.g. 8093.

---

## §7 Definition of done (V0)

- All 9 milestones VERIFY-green; backend unit+integration pass; FE vitest pass; Playwright smoke opens the Composition tab and co-writes one grounded scene with a visible critic flag.
- Live-smoke run OR explicitly deferred (D-COMP-V0-LIVE-SMOKE) with reason.
- Contract committed before FE; gateway routes; compose+db-init wired.
- §11 fixes verifiably present (4 targeted tests).
- **§12 review fixes verifiably present:** L1b in-world cutoff test · L4 reading-order-drop + `l4_dropped_no_position` log test · Mk `chapter_index` populated (unit + live re-ingest) · BookProfile NEUTRAL-default + source_language threaded · A1 `project_id`-non-null assertion · token-metering empty-frame fallback · tolerant `violations[]` parse · critic model ≠ drafter.
- **§13 benchmark fixes verifiably present:** mandatory `expected_draft_version` → 409 conflict (PS2/OI-2) · ownership chokepoint before internal reads (SEC2) · `<lore>`+`<guide>` sanitized (SEC3) · cancel-in-flight + idempotency (S2) · re-resolve active canon rules at critique (CC2) · canon-rule window validation (CR4) · cache glossary entity_id + soft-absent (DI3) · no-knowledge-project surfaced (C3a) · debounced autosave never ghost (SC4) · anchor-id re-resolve on accept (E2).
- SESSION_HANDOFF updated; clean commits per milestone.
