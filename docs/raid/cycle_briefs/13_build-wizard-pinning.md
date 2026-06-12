# Cycle 13: Build wizard — glossary pinning

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Pin a chosen set of glossary entities so they're force-injected into the `known_entities` prompt context of **every** extraction window regardless of whether they appear in that chapter — so sparse-but-critical entities (a god in ch1 & ch5000) are always anchored. Per DESIGN_C12_C13: **knowledge path is additive** (prepend pinned names to `known_entities` at each `_run_pipeline` call site — pinning = name-prefix injection, not a new prompt block); **worker-ai gets a NEW `GlossaryClient.fetch_entities_by_ids` method** (client already wired for glossary_sync, only the batch-fetch is new) to replace its hardcoded `known_entities=[]`; **auto-pin** needs a NEW glossary-service `GET /internal/books/{id}/entities/stats` (span+coverage GROUP-BY over `chapter_entity_links`); a **pinned-injection cost line** added to the estimate; **Step-2 dual-list pinning UI**. Cross-service (knowledge-service + worker-ai + glossary-service). The wizard shell is built in C12 — this adds Step-2.
- **Acceptance gate:** `scripts/raid/verify-cycle-13.sh` exits 0
- **Top 3 LOCKED decisions consumed:** C13-pin-name-prefix-injection, C13-workerai-fetch_entities_by_ids, C13-autopin-via-glossary-stats-endpoint
- **DPS count:** 4
- **Estimated wall time:** 6–8h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C12
- Files expected to exist (grep-able paths): the 3-step build-wizard shell + `targets`/`concurrency_level` threading from C12; knowledge-service `extraction.py` StartJobRequest + `pass2_orchestrator` `_run_pipeline` + the existing `glossary_client.fetch_entities_by_ids`; worker-ai `GlossaryClient` (wired for glossary_sync) + runner; glossary-service `chapter_entity_links` table + `/internal/books/{id}/...` route module.

## Scope (IN)
- **Contract + storage:** add `pinned_glossary_entity_ids: list[str]` to knowledge-service `StartJobRequest`; migration `extraction_jobs ADD COLUMN pinned_entity_ids JSONB` (default null = back-compat).
- **Knowledge path (additive):** at job start fetch pinned entities via the existing `glossary_client.fetch_entities_by_ids(...)`; prepend the pinned **names** as a prefix into `known_entities` at every `_run_pipeline` call site so they reach every window's `extract_entities` call + the prompt template.
- **worker-ai path (THE GAP):** add `GlossaryClient.fetch_entities_by_ids(book_id, entity_ids)` (mirror the knowledge-service method; same `X-Internal-Token`, **no new secret**). Read `pinned_entity_ids` from the job row → fetch names → replace the hardcoded `known_entities=[]` in the runner.
- **Auto-pin endpoint (NEW, glossary-service):** `GET /internal/books/{book_id}/entities/stats` → bounded GROUP-BY over `chapter_entity_links` returning `{entity_id, name, kind, mention_count, first_chapter_index, last_chapter_index, coverage_pct}`. Heuristic (FE/BE): suggest where `coverage_pct ≤ 0.15` AND `span ≥ 0.5×chapter_count` (sparse + long-reaching; thresholds tunable).
- **Cost model:** add a `pinned_count × ~50 tokens × num_windows` line to the build estimate (the dominant "pinned context injection" driver — must be visible).
- **FE Step-2 dual-list:** available ↔ pinned with search/type/frequency filters + auto-pin suggestion banner (from the stats endpoint) + per-window token budget; posts `pinned_glossary_entity_ids`. Reuses existing entity-list patterns.
- `scripts/raid/verify-cycle-13.sh` (acceptance gate; runner creates it) + Playwright screenshot of the Step-2 dual-list pinning UI.

## Scope (OUT — explicitly)
- **NO target-typed extraction** — `targets[]`, `concurrency_level`, the conditional gather, the wizard **shell** are all **C12** (this cycle adds Step-2 into the existing shell).
- **NO separate pinned prompt block** — pinning is name-prefix injection into `known_entities` only (reuse the proven seam).
- **NO new secret / new auth** — worker-ai `fetch_entities_by_ids` reuses the existing `X-Internal-Token`.
- No timeline (C14); no graph canvas; no glossary review-system changes beyond the read-only stats endpoint.

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass:
  - Knowledge unit: pinned names appear in `known_entities` for a window whose chapter text does NOT mention them.
  - worker-ai unit: `fetch_entities_by_ids` returns names; `known_entities` is no longer empty when a pinned set is present.
  - glossary unit: stats endpoint returns correct `first/last_chapter_index`, `mention_count`, `coverage_pct` on a fixture book.
  - Cost-estimate unit: pinned-injection line equals `pinned_count × ~50 × num_windows`.
- Lints pass: ruff/black on knowledge-service + worker-ai + glossary-service; `python scripts/ai-provider-gate.py` green (extraction LLM/embedding resolve via provider-registry; no hardcoded model names).
- **Live smoke (REQUIRED — cross-service):** evidence string contains `live smoke: 2 pinned entities absent from chapter N → both appear in chapter N extraction prompt`. Build with 2 pinned entities absent from chapter N → confirm both appear in chapter N's extraction prompt (wire-capture or log assert). If full stack un-bootable: `live infra unavailable: <reason>`.
- Playwright screenshot: Step-2 dual-list pins an entity + the auto-pin banner renders.

## DPS parallelism plan
- DPS 1 (knowledge BE): StartJobRequest field + `pinned_entity_ids JSONB` migration + prepend pinned names into `known_entities` at every `_run_pipeline` call site + cost line (return budget: 1500 tokens summary)
- DPS 2 (worker-ai): add `GlossaryClient.fetch_entities_by_ids` + read `pinned_entity_ids` → replace `known_entities=[]` in runner
- DPS 3 (glossary BE): new `GET /internal/books/{id}/entities/stats` GROUP-BY over `chapter_entity_links` + fixture-book test
- DPS 4 (FE): Step-2 dual-list + auto-pin banner (consumes stats endpoint) + per-window budget; Playwright shot
- **Serial tail (Raid Leader):** rebuild touched images → 2-pinned-absent-from-chapter-N live smoke → `verify-cycle-13.sh`

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Pinned names not in EVERY window:** injection applied at job start but missed at some `_run_pipeline` call site → sparse entities still drop out of chapters that don't mention them (defeats the whole feature). Confirm every window's `known_entities` carries the prefix.
- **worker-ai still `[]`:** the new `fetch_entities_by_ids` added but the runner's hardcoded `known_entities=[]` left in place, or fetch never invoked when a pinned set is present.
- **New secret introduced:** `fetch_entities_by_ids` adding a per-service URL/token instead of reusing `X-Internal-Token` → provider/secret invariant drift.
- **Stats endpoint span/coverage math:** `coverage_pct` / `first/last_chapter_index` computed off the wrong key or unbounded query → wrong auto-pin suggestions or a slow scan.
- **Mock-only false-green:** units green but no real build with absent-pinned-entities ran → confirm the live-smoke token reflects a genuine wire/log capture.
- **Cost line missing/wrong:** pinned-injection cost omitted from the estimate or not scaling with windows.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present (contract+storage + knowledge prepend + worker-ai fetch method + glossary stats endpoint + cost line + Step-2 dual-list)
- No OUT items touched (no C12 target-gating, no separate prompt block, no new secret, no C14)
- All acceptance criteria met (units + provider-gate + live-smoke token + Playwright shot)
- Cross-cycle invariants not violated (additive knowledge path; reuses `X-Internal-Token`; provider invariant held)

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Detailed design: [DESIGN_C12_C13.md](../../plans/2026-06-13-creation-unblock/DESIGN_C12_C13.md) — C13 section (knowledge additive half + worker-ai gap + auto-pin endpoint + cost + FE dual-list + locks).
- Cycle row: [CYCLE_DECOMPOSITION.md](../../plans/2026-06-13-creation-unblock/CYCLE_DECOMPOSITION.md) — C13 row + "Build wizard is C12+C13 (split)" note.
- LOCKED decisions: [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-06-13-creation-unblock/OPEN_QUESTIONS_LOCKED.md) — §Architecture-review locks "C13 = M–L (DESIGNED)"; §Knowledge cycle design "C13 pinning".
- Backend audit: [2026-06-13-knowledge-design-vs-impl-gap.md](../../specs/2026-06-13-knowledge-design-vs-impl-gap.md).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Top LOCKED 1:** pinning = **name-prefix injection** into `known_entities` (not a separate prompt block) — applied at EVERY window via every `_run_pipeline` call site.
- 🔴 **Top LOCKED 2:** worker-ai gets a NEW `GlossaryClient.fetch_entities_by_ids` (client already wired; only batch-fetch is new) — reuse `X-Internal-Token`, **no new secret**.
- 🔴 **Top LOCKED 3:** auto-pin ships in C13 via a NEW glossary `GET /internal/books/{id}/entities/stats` (span+coverage GROUP-BY over `chapter_entity_links`); pinned-injection cost is its own estimate line.
- 🔴 **Acceptance MUST include:** the cross-service live-smoke token `live smoke: 2 pinned entities absent from chapter N → both appear in chapter N extraction prompt` — mock-only is a false-green.
- 🔴 **Do NOT touch:** C12's target-gating / `concurrency_level` / wizard shell — this cycle only adds Step-2 into the existing shell; no hardcoded model names (provider-registry resolution).
- 🔴 **Fresh session reminder:** this is a new `/raid 13` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
