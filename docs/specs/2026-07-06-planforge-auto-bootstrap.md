# PlanForge auto-bootstrap — CLARIFY + DESIGN (2026-07-06)

> **Status:** DESIGN draft, POC scope proposed, **no BUILD started**. Follows
> `D-PLANFORGE-GUI-AUDIT` (P0 crash fix + leaky-abstraction UX redesign,
> `design-drafts/planforge/2026-07-06-planner-panel-redesign-mockup.html`).

## 1. The question that triggered this

User: *"tôi có book trống, giờ tôi có plan do tự viết hoặc tham khảo từ đâu đó
quăn vào — mọi thứ trống trơn, không có ontology, kg scheme, arc, chapter,
scene, beat — vậy plan sẽ xử lý ntn? có khả năng tạo mọi thứ từ scratch
không?"* (I have an empty book, I paste a self-written or sourced plan in —
everything is empty, no ontology, no KG schema, no arc/chapter/scene/beat. How
does the plan handle this? Can it create everything from scratch?)

**Answer, code-grounded (two research passes, file:line evidence in §2):
no, not today.** `compile()` produces a JSON `PlanningPackage` and, only if
`run_pipeline=true`, seeds a handful of Glossary character entities via a
call that **ignores the spec's own already-parsed character data**. It never
creates a single real `Chapter` row in book-service, regardless of any flag.
"Scene" and "Beat" have no persisted, editable representation anywhere in the
architecture — Scene is a read-only import-time index that gets flattened
back into one chapter body; Beat is a pure in-memory planning concept that
never survives past the pipeline's JSON output.

## 2. Current architecture, as verified (not assumed)

| Artifact | Created by PlanForge today? | Evidence |
|---|---|---|
| `PlanningPackage` JSON (premise/canon/planner_state/constraints/events/`chapters[]`/genre_tags) | ✅ always, on `compile()` | `app/engine/plan_forge/compile.py:8-113` |
| `composition_works` row | ✅ always | `plan_forge_service.py:655,697-715` |
| Glossary **character** entities (Postgres) | ⚠️ only if `run_pipeline=true`, via an **independent, spec-blind** `propose_cast` LLM call | `plan_forge_service.py:667-693` → `operations.py:111-137` → `planning_pipeline.py:69-87` |
| Glossary **concept/mechanic** entities | ❌ never — `compile_artifacts`'s own `glossary_seeds` (chars+mechanics, built from the ACTUAL spec) is computed and stored in the artifact but never POSTed anywhere | `compile.py:12-34,103` (dead data, confirmed via repo-wide grep) |
| Neo4j KG nodes | ⚠️ only chained off the glossary write above, only if Neo4j is configured; **silent no-op** in Track-1/no-Neo4j deployments | `knowledge-service/app/events/handlers.py:610,686,719` |
| Real `Chapter` rows (book-service) | ❌ **never**, in any mode — no plan_forge/planning_pipeline code calls book-service's `createChapter` | confirmed zero references to `book_client` in `plan_forge_service.py`, `planning_pipeline.py`, `plan_heal.py`, `grounded_plan.py`; `book_client.py` itself has no `create_chapter` method at all |
| `scenes` rows (book-service) | ❌ never from planning — this table is populated ONLY by the document-**import** parser, then immediately flattened back into one chapter body; it's a read-only index for KG extraction, not an editable unit | `book-service/internal/api/parse.go:176-184`, `scenes.go:41-101` |
| "Beat" as persisted data | ❌ never, anywhere — exists only as transient dicts/dataclasses inside the Stage 0-5 pipeline's in-memory objects, serialized only into the job's own JSON result | `app/engine/plan.py:62-111`, `worker/operations.py:108,137` |
| Ontology / entity-kind schema | N/A — this is a **global** DB seed (12 default kinds), not a per-book bootstrap concern | `glossary-service/internal/migrate/migrate.go:566-597` |

**The smallest real, user-editable unit of manuscript content is the whole
Chapter's Tiptap JSON body.** There is no persisted scene- or beat-level
editing unit anywhere in the current system — this is a real architectural
fact the auto-bootstrap design must respect, not fight.

**Chapter drafting is already a separate, working action** (`run_chapter_generate`,
`operations.py:428-462`) — but it *requires* an existing `chapter_id` as
input. It was never designed to receive one it created itself.

## 3. Proposed multi-step "Planner Auto-Bootstrap" workflow

Per the user's direction: encourage the multi-step auto-bootstrap workflow,
but **POC first, built rigorously** — this spans 3 services and several
currently-disconnected subsystems, correctly sized **XL** per this repo's
Task Size Classification (13+ logic changes, cross-service side effects).

```
compile()  →  [A] create chapter shells  →  [B] seed glossary from the REAL spec
                        │                              │
                        └──────────────┬───────────────┘
                                        ▼
                         [C] attach Stage 0-5 scene/beat plan
                             as PER-CHAPTER drafting context
                                        │
                                        ▼
                    [D] run_chapter_generate per chapter
                        (existing action, now reachable)
                                        │
                                        ▼
                [E] KG sync (existing, automatic once B is correct)
```

**[A] Create chapter shells (NEW).** Walk `package.chapters[]`
(`{title, ordinal, event_id}`); for each, call book-service's
`POST /v1/books/{id}/chapters` (currently unused by any planning code) to
create a real `Chapter` row; capture the returned `chapter_id`; persist an
`event_id ↔ chapter_id` mapping (new artifact kind or a join table — TBD in
DESIGN) so downstream steps and the GUI can resolve "this planned scene is
this real chapter." **This is the foundational bridge — nothing else in this
workflow can work without it, and it's the piece with zero prior art to lean
on** (no existing code creates chapters programmatically today).

**[B] Seed glossary from the real spec (FIX, not new).** Replace (or
reconcile with) `propose_cast`'s spec-blind re-derivation: POST the
already-computed, already-correct `glossary_seeds` (`compile.py:12-34` —
characters AND mechanics/concepts) that today are silently discarded. This
closes a real, separate bug found during this investigation, independent of
whether the rest of the auto-bootstrap workflow ships.

**[C] Scene/beat as drafting context, not as new DB rows (respects the
architecture, doesn't fight it).** Since no persisted scene/beat unit exists
or should be invented (that's a bigger, separate architectural change this
doc does NOT propose), the Stage 0-5 pipeline's per-chapter scene/beat plan
becomes **input context** to that chapter's `run_chapter_generate` call —
exactly the role Stage 0-5 already has one level below PlanForge, just
finally wired to a REAL `chapter_id` instead of staying inert JSON.

**[D] Reachable chapter drafting (existing action, new reachability).** Once
[A] produces real chapter_ids, the already-built `run_chapter_generate` can
be invoked — either the user opens the newly-created (empty) chapter and
clicks the existing "draft" action per-chapter, or (a later increment, not
POC) an explicit opt-in "auto-draft every chapter" bulk action.

**[E] KG sync (no new code).** Automatic once [B] is fixed, exactly as it
works today for the one thing that already gets seeded correctly (characters,
when Neo4j is configured). No new work — a correctness fix in [B] is what
was actually missing.

## 4. Recommended POC scope (before committing to the full workflow)

Per the user's "POC first, rigorous" direction, do **NOT** build all five
steps at once. The one true unknown — and the one nothing in the codebase has
ever done — is **[A] alone**: creating real book-service chapters
programmatically from a compiled package and correctly round-tripping the
`event_id ↔ chapter_id` mapping back through composition-service's own
artifact storage.

**POC scope: [A] only.**
- Given a compiled `PlanningPackage` for a real arc (reuse the story-plan-v1
  fixture / an existing `Ma Nữ Nghịch Thiên (POC)` book run), call
  book-service's `createChapter` once per `package.chapters[]` entry.
- Persist the `event_id ↔ chapter_id` mapping as a new artifact (kind e.g.
  `"chapter_map"`) on the plan run.
- Verify live: the created chapters actually appear in the Studio's
  Manuscript Navigator / Chapter Browser for that real book (not just a 200
  response) — same "verify by actually looking" discipline as the rest of
  this session's PlanForge work.
- Explicitly OUT of POC scope: [B] (glossary fix), [C]/[D] (drafting context
  + reachability), bulk auto-draft. These become their own scoped
  PLAN/BUILD passes once [A] is proven, per this repo's "large effort → one
  continuous classified run, not five ad-hoc patches" guidance.

**Open questions for the next CLARIFY checkpoint before BUILD even on the
POC:**
1. Where does the `event_id ↔ chapter_id` map live — a new `plan_artifact`
   kind (cheapest, matches existing patterns) or a new dedicated table
   (more queryable, more migration overhead)?
2. Ordinal collisions — what happens if the book already has chapters (not
   truly empty) when chapter-shell creation runs? Append after the highest
   existing ordinal, or require an explicitly-empty book for POC purposes?
3. Idempotency — if `compile()` is called twice for the same run (a real
   flow: propose → tweak → re-validate → re-compile), does step [A] skip
   chapters it already created, or would a naive implementation double them?

## 5. Explicit non-goals (this doc, this POC)

- **Not** inventing a persisted Scene/Beat DB entity. The architecture's
  actual smallest editable unit (the whole chapter) is respected as a design
  constraint, not treated as a gap to fix.
- **Not** touching the Planner GUI redesign mockup's "Done" screen copy yet —
  once [A] is POC'd and a real decision is made about scope/timeline, the
  mockup's "Start drafting in Compose →" claim should be revisited to match
  whatever is actually true at that point (a separate, cheap doc-fix, not
  blocking this design).
- **Not** a single big-bang migration — [A]→[B]→[C]/[D] are sequenced,
  separately scoped PLAN/BUILD passes, matching the repo's "no deadline, no
  defer drift" methodology for large efforts.
