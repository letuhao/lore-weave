# Cycle 23: Derivative schema + API (composition)

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Ship the **dị bản M0** copy-on-write substrate in **composition-service**: add `source_work_id` + `branch_point` columns to `composition_work`; create `divergence_spec` + `entity_override` tables; expose **`POST /works/{id}/derive`** that creates a derivative Work linked to a source + its divergence spec — **spec only, no chapter clone**. The derivative is created with **its own new knowledge `project_id`** (G2 partition = the delta). **ARCH-REVIEW GUARD: derivative Work `project_id` is NOT-NULL enforced** at schema + API level. Migration up/down clean + round-trip.
- **Acceptance gate:** `scripts/raid/verify-cycle-23.sh` exits 0
- **Top 3 LOCKED decisions consumed:** G2 (derivative owns its own project_id partition), G3 (chapter-level branch_point), ARCH-REVIEW GUARD (project_id NOT NULL)
- **DPS count:** 2
- **Estimated wall time:** 3–4h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C0
- Files expected to exist (grep-able paths): `services/composition-service/` migrations dir; `composition_work` table + the `works.py` create path that provisions a knowledge project before the Work row.

## Scope (IN)
- **Migration (up):** `composition_work` gains `source_work_id` (nullable FK self-ref) + `branch_point` (chapter-level, per G3); new tables `divergence_spec` (work_id, taxonomy/type, `pov_anchor` nullable, added `canon_rule[]`) and `entity_override` (work_id, target entity ref, overridden fields JSON). `targets`/override fields stored as the service's standard array/JSON columns.
- **Migration (down):** clean reverse — drops the two tables + the two columns; round-trip (up→down→up) leaves no residue.
- **`POST /works/{id}/derive`:** validate source Work exists + caller owns it; **create a NEW knowledge project_id** for the derivative; insert the derivative `composition_work` row with `source_work_id`=source, `branch_point`, and the **NOT-NULL `project_id`**; persist the `divergence_spec` + any `entity_override[]` from the request body. **No chapter clone** — reference spine stays read-only on the source.
- **GUARD enforcement:** `project_id` column is `NOT NULL`; the derive endpoint rejects (4xx) any attempt to create a derivative with a null/absent `project_id`. Unit test asserts the rejection.
- `scripts/raid/verify-cycle-23.sh` (acceptance gate) — asserts migration up/down clean, derive creates a linked spec'd Work, null project_id rejected.

## Scope (OUT — explicitly)
- **NO chapter/scene cloning.** No copy-paste of source prose (LOCKED: reference spine is read-only, writer adapts manually).
- **NO packer override-merge** — that is C25. This cycle only persists the override rows; it does not apply them at retrieval.
- **NO critic enforcement** (C26), **NO delta flywheel / what-if promotion** (C27), **NO living-world FE** (C28).
- **NO FE** — the divergence wizard + studio is C24. This is BE schema+API only.
- **NO knowledge/glossary/book migration** — dị bản is composition-only schema (LOCKED COW).
- NO relationship/event overrides (M0 override scope = entity fields + added canon rules only).

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: composition-service unit suite for the derive endpoint + the override/spec persistence (`services/composition-service/.../test_derive*.py`).
- Lints pass: composition-service linter; provider-gate green (no new provider SDK / hardcoded model — composition has no AI imports, keep it that way).
- Integration smoke: **migration up/down clean + round-trip** (up→down→up no residue); **null project_id rejected** (the GUARD). Migration cycle is the verify for this BE-migration cycle — no live cross-service token required, but evidence string carries `migration round-trip clean + null project_id rejected`.

## DPS parallelism plan
- DPS 1: **Migration + schema** — `composition_work` columns + `divergence_spec`/`entity_override` tables, up + down + round-trip test. (return budget: 1500 tokens summary)
- DPS 2: **`POST /works/{id}/derive` API** — ownership validate, new project_id provision, derivative row + spec + overrides insert, **NOT-NULL project_id guard + rejection path**, unit tests. Depends on DPS 1 schema shapes — seam-stub the table names first, integrate last.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **GUARD bypass:** any code path that can insert a derivative `composition_work` with a null/absent `project_id` (DB constraint missing, or API not provisioning a new project) → cross-project grounding leak (the timeline endpoint widens to ALL projects on null). This is the #1 thing to verify.
- **Accidental clone:** derive that copies source chapters/scenes instead of referencing — violates COW + reference-spine LOCKED.
- **Down-migration dirtiness:** down that leaves a column/table/index behind, or up→down→up that fails — assert true round-trip.
- **project_id reuse:** derivative sharing the SOURCE's project_id instead of a fresh one → no delta partition, breaks G2 isolation.
- **Override scope creep:** persisting relationship/event overrides (deferred) instead of only entity-field + canon-rule overrides.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
CLEAR iff: only composition-service migration + derive API + tests + `scripts/raid/verify-cycle-23.sh` changed; `project_id` is NOT NULL at schema AND API; derive persists spec+overrides with NO chapter clone; migration up/down round-trips clean; no knowledge/glossary/book schema touched; no FE; no packer/critic/flywheel logic. Otherwise BLOCKED.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- CYCLE_DECOMPOSITION.md — **C23** row (dị bản M0).
- OPEN_QUESTIONS_LOCKED.md — **§G2** (derivative own project_id = own Neo4j partition), **§G3** (chapter-level branch_point), **dị bản locks** (COW, override scope, reference spine, ownership), **Architecture-review locks** (GUARD: derivative project_id NOT NULL; source_work_id join provided by C23).
- `docs/specs/2026-06-13-derivative-works-living-world-plan.md` — dị bản M0.

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **GUARD (LOCKED):** derivative Work `project_id` is **NOT NULL** at schema + API. A null project_id widens the knowledge timeline endpoint to ALL projects → cross-project grounding leak. Reject it.
- 🔴 **G2 (LOCKED):** derivative gets its **OWN new project_id** = its own Neo4j delta partition. Never reuse the source's project_id.
- 🔴 **COW (LOCKED):** spec only, **NO chapter clone**. The source reference spine is read-only; the writer adapts manually.
- 🔴 **Acceptance MUST include:** migration **up/down clean + round-trip** AND the **null project_id rejected** test — both are the verify, easy to forget the down-migration.
- 🔴 **Do NOT touch:** knowledge/glossary/book schema (composition-only); no packer (C25)/critic (C26)/flywheel (C27)/FE (C24).
- 🔴 **Fresh session reminder:** this is a new `/raid 23` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
