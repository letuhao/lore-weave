# Cycle 24 — Playwright genderbend smoke: BLOCKED by a C23 BE defect

## What the FE proved (all green)
Drove the wizard end-to-end as `claude-test@loreweave.dev` on **万古神帝** (book
`019eb60e-…`, source Work project `019eb683-…`), chapter 1 editor → Compose panel:

1. **Studio launch** — `⑂ Spawn dị bản` button renders in the co-writer studio toolbar.
   → `wizard-step1-source-branch.png`
2. **Step 1 (Source + branch_point, G3)** — chapter-level branch picker listing the
   book's 5 real chapters; picked 第3章 黄极境.
3. **Step 2 (divergence type, UX §7.1)** — 3 type cards; picked **Character transform**
   (genderbend). → `wizard-step2-character-transform.png`
4. **Step 3 (overrides preview)** — REAL canon entities from the source project
   (张若尘, 林妃, 池瑶, …); overrode **张若尘 → "now a woman — reborn female (genderbend)"**.
   → `wizard-step3-override-genderbend.png`
5. **Step 4 (name)** — named "Genderbend AU — 张若尘 as a woman". → `wizard-step4-name.png`
6. **Submit** → `POST /v1/composition/works/019eb683-…/derive` — the FE→gateway→BE wiring
   is correct: the request reached the composition-service derive endpoint with the
   right body (taxonomy=character_transform, branch_point, entity_overrides).

The wizard, the relative `/v1/composition` call, and the gateway wildcard-proxy of
`/v1/composition` (no gateway change needed — confirmed) all work.

## What blocked it (UPSTREAM — C23 BE defect, NOT a C24 FE issue)
`POST /works/{id}/derive` returned **500 UniqueViolationError** on
`uq_composition_work_project`:

```
duplicate key value violates unique constraint "uq_composition_work_project"
DETAIL:  Key (project_id)=(019eb683-…) already exists.
  File "/app/app/routers/works.py", line 345, in derive_work
    work = await works.create_derivative(...)
```

Root cause (cross-service): C23's `KnowledgeClient.create_project` POSTs
`{"project_type":"book","book_id":…}`. knowledge-service `ProjectsRepo.create_or_get`
**dedupes per (user, book)** for `project_type='book'` (the D-COMP-POST-WORK-RACE
guard) and returns the SOURCE project (`created=False`) instead of a fresh one. So
the derivative is handed the source's own project_id → `create_derivative` inserts a
second composition_work row with that project_id → violates `uq_composition_work_project`.

**G2 ("a derivative gets its OWN fresh knowledge project_id = its own Neo4j delta
partition") is structurally unsatisfiable via the current create_project path** for any
book that already has a Work. C23's live migration round-trip never exercised the real
knowledge round-trip (it tested the DB CHECK + schema), so this surfaced only now under
the C24 live UI smoke — the canonical "live-smoke catches a cross-service contract bug
that unit/mock coverage hid" case.

Note: a stale composition-service image (pre-C23, no derive route) gave a first 404
`{"detail":"Not Found"}`; rebuilt + `up -d composition-service` (derive route now in the
running openapi). The retry then surfaced the real 500 above. → `derive-blocked-c23-dedup-500.png`

## Minimal C23/knowledge fix (out of C24 FE scope — needs the upstream owner)
Knowledge-service must offer a path that mints a FRESH `book`-typed project even when
one already exists (a derivative is intentionally a *second* graph for the book), e.g.:
- a `?force_new=true` / `allow_duplicate=true` param on `POST /v1/knowledge/projects`
  that skips the create_or_get dedup, **or**
- a distinct project flavour for derivatives (e.g. `project_type='derivative'`, or carry
  a `source_project_id`) that is exempt from the per-(user,book) advisory-lock dedup,
and C23's `create_project` call passes it on the derive path.

Either is a small, additive BE change to C23 + knowledge — analogous to how C21's
design_gap was cleared by a C20 follow-up commit. It is explicitly OUT of the C24
FE-only scope (NO C23 schema/API edit allowed).

---

## RESOLVED 2026-06-15 — Step-A BE fix landed (own commit), smoke re-run GREEN

The upstream defect was fixed in a SEPARATE Step-A commit (knowledge-service +
composition-service): additive `is_derivative` column + a `force_new` field on
`ProjectCreate`; `create_or_get` short-circuits to a plain insert when `force_new`
(skips the per-(user,book) dedup) and stamps `is_derivative=true`; the dedup SELECT +
`get_by_book` exclude `is_derivative`. C23's `derive_work` now calls
`create_project(..., force_new=True)`. Default false ⇒ greenfield POST /work unchanged.

**playwright: genderbend dị bản spawned + studio badges shown** — with the BE rebuilt
+ restarted + migrated, the SAME wizard flow on 万古神帝 (branch 第3章, type=
character_transform, overrode 张若尘 → "now a woman (genderbend)", named "Genderbend AU —
张若尘 as a woman") submitted **`POST /v1/composition/works/019eb683-…/derive` → 201**
(was 500). The studio switched to the derivative Work and rendered:
- **Derivative banner**: "You are writing a dị bản (derivative) · branches at chapter 4 ·
  Original chapters are a read-only reference — adapt them manually."
- **2-layer grounding badges + legend**: 张若尘 → **OVERRIDDEN** (✎, the real submitted
  delta); every other canon entity → **INHERITED** (⛓). Badge reflects real persisted
  override state, never a guess.
- **Reference spine (read-only)**: source chapters 1-3 (≤ branch point) listed with
  "Open" links only — NO auto-insert into the draft (LOCKED honoured).

DB confirms G2: the UI-spawned derivative project `019ec734-…` is `is_derivative=t` and
DISTINCT from the source's `019eb683-…` (two earlier curl-driven derives → two more
distinct projects). Screenshot: `genderbend-dibang-studio-badges.png`. 0 console errors.
