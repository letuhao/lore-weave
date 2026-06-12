# Cycle 8: Entities semantic layer (BE+FE)

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Add the **semantic-entity layer** to knowledge-service's entities surface. BE: derive a `status` field (`canonical`/`discovered`/`archived`) from existing columns, add a `semantic_query` (vector) param, a `status` filter, and `sort_by=anchor_score`. The Entity already carries `anchor_score`, `glossary_entity_id`, `archived_at` — no new column. FE: render ⭐ (canonical) / 💭 (discovered) / 📦 (archived) rows + an anchor-score badge + a status legend + a semantic-search box, all **inside the C6 project-detail shell scoped by route (G6)** — the per-tab project `<select>` is **removed** when route-scoped (survives only on the optional cross-project search surface).
- **Acceptance gate:** `scripts/raid/verify-cycle-8.sh` exits 0
- **Top 3 LOCKED decisions consumed:** C8-entity-status, Knowledge-design-parity, G6
- **DPS count:** 3
- **Estimated wall time:** 5h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C7
- Files expected to exist (grep-able paths): `services/knowledge-service/app/api/entities.py` (or equivalent entities route), the C6 project-detail shell route `/knowledge/projects/:projectId/:section`, the entities tab component that already accepts a `projectFilter`.

## Scope (IN)
- **BE** — entities list/query endpoint: compute a **derived `status`** server-side (`canonical` = `glossary_entity_id` set · `discovered` = unanchored · `archived` = `archived_at` set). NO new DB column.
- **BE** — new **`semantic_query`** param → vector/embedding search over entities; plain `search` stays FTS. Embedding identity resolved via **provider-registry** (no hardcoded model name).
- **BE** — `status` filter param (`canonical|discovered|archived`) + `sort_by ∈ {anchor_score, mention_count}`.
- **FE** — entity rows show ⭐/💭/📦 by status + an **anchor-score badge** + a **legend** explaining the three states + a **semantic-search box** (distinct from plain search).
- **FE** — render inside the **C6 project-detail shell**, `projectId` from the **route**; **remove** the project `<select>` when scoped (G6). The select survives only on the demoted cross-project search surface.
- `scripts/raid/verify-cycle-8.sh` (acceptance gate, runner creates it).

## Scope (OUT — explicitly)
- **NO promote / link-to-glossary** wiring — that is C9.
- **NO gap report** (`find_gap_candidates` / `GET /projects/{id}/gaps`) — that is C10.
- **NO proposals inbox** aggregation — that is C11.
- No new `status` column / migration — `status` is derived, not stored.
- No timeline / importance work (C14); no build-wizard changes (C12/C13).
- Do NOT add a per-service embedding `*_URL`/`*_MODEL` env — embedding resolves via provider-registry only.

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: knowledge-service entities pytest — derived-`status` mapping (all 3 cases), `status` filter, `sort_by=anchor_score`, `semantic_query` path returns vector-ranked results.
- Lints pass: provider-gate green (no hardcoded model literal in the semantic-query embedding path).
- Integration smoke: **live smoke (cross-service, REQUIRED)** — on a **built graph**, a `semantic_query` returns correct entities AND a `status` filter returns only matching-status entities. Evidence string contains `live smoke: semantic_query + status filter on a built knowledge graph`. Plus a **Playwright screenshot** of the ⭐/💭/📦 rows + anchor badge + legend inside the scoped C6 shell.

## DPS parallelism plan
- DPS 1: BE derived-`status` + `status` filter + `sort_by=anchor_score` over existing columns (return budget: 1500 tokens summary).
- DPS 2: BE `semantic_query` vector path + provider-registry embedding resolution (seam-stub the embed client, integrate last).
- DPS 3: FE — ⭐/💭/📦 rows, anchor badge, legend, semantic-search box, route-scoped rendering + `<select>` removal in the C6 shell.
- Serial tail (Raid Leader): live-smoke on a built graph + Playwright screenshot + `verify-cycle-8.sh`.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Hardcoded model name** in the `semantic_query` embedding path — must resolve via provider-registry (ENFORCED invariant).
- **Status derivation precedence:** if both `archived_at` and `glossary_entity_id` are set, which wins? Confirm the lock's order is honored consistently BE+FE.
- **Mock-only false-green:** semantic query "passes" but no real embedding call ran on a stacked-up service — confirm the live-smoke token reflects a genuine built-graph query.
- **`<select>` not removed when route-scoped** (G6) — the dropdown must disappear in the project-detail shell, surviving only on the cross-project surface.
- **New column smuggled in:** any migration adding a `status` column violates the lock (status is derived).
- **Cross-project bleed:** route-scoped entity query must filter by the route `projectId`, not leak other projects.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present (derived status, semantic_query, status filter, sort_by=anchor_score, ⭐/💭/📦 + badge + legend + search box, route-scoped).
- No OUT items touched (no promote, no gap report, no proposals, no new column).
- All acceptance criteria met incl. live-smoke token + Playwright shot.
- Cross-cycle invariants not violated: provider-registry embedding, no hardcoded model, G6 select removal.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- CYCLE_DECOMPOSITION.md — C8 row (Entities semantic layer) + cross-service live-smoke note.
- OPEN_QUESTIONS_LOCKED.md — **C8 entity status** lock, **Knowledge design-parity** locks, **G6** (IA / route-scoping).
- `docs/specs/2026-06-13-knowledge-design-vs-impl-gap.md` — semantic-entity layer gap (design §3).
- `docs/specs/2026-06-13-knowledge-service-standalone-ux-review.md` — entities UX (status rows, anchor badge, legend).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **C8 entity status LOCKED:** `status` is **derived** server-side (`canonical`=glossary_entity_id set · `discovered`=unanchored · `archived`=archived_at set) — **no new column**.
- 🔴 **Provider invariant:** `semantic_query` embedding resolves via **provider-registry**; NO hardcoded model name, NO per-service embed URL/MODEL env.
- 🔴 **G6 LOCKED:** render inside the C6 project-detail shell, `projectId` from the **route**; **remove** the project `<select>` when scoped (keep it only on the cross-project search surface).
- 🔴 **Acceptance MUST include:** the cross-service live-smoke token `live smoke: semantic_query + status filter on a built knowledge graph` (real call, not mocked) + a Playwright screenshot.
- 🔴 **Do NOT touch:** promote/link-to-glossary (C9), gap report (C10), proposals inbox (C11), timeline (C14).
- 🔴 **Fresh session reminder:** this is a new `/raid 8` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
