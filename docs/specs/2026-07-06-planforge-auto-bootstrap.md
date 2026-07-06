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
compile()  →  PROPOSE (one LLM/deterministic pass, no side effects)
                        │
                        ▼
             persist a Bootstrap Proposal record (pending)
                        │
                        ▼
              ─── human review + approve/reject ───
                        │  (approved)
                        ▼
              APPLY (deterministic, zero LLM calls)
                 ├─ [A] create chapter shells
                 ├─ [B] seed glossary from the REAL spec
                 └─ [ontology gaps] create missing kind(s)/attribute(s)
                        │
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

### 3.1 The propose → record → approve → apply gate (structural-mutation quarantine)

User's explicit direction: *"cần có cơ chế dry run và lưu record để khi user
approve thì apply change... LLM chỉ lên plan 1 lần... user approve thì update
plan, update KG/ontology... không chạy lại LLM nhiều lần"* (need a dry-run
mechanism with a saved record — the LLM plans ONCE, proposes the missing
pieces, the user approves, THEN the system applies changes to the plan/KG/
ontology — never re-running the LLM multiple times).

This is not a new pattern for this repo — it's the same shape as Enrichment's
mandatory quarantine + human promote (H0: gap-detected → generate →
canon-verify → **quarantined proposal** → human review → **promote** →
reversible retract) and PlanForge's own `plan_apply_revision` honesty
contract (`applied`/`no_change`/`rejected`, never silently mutating). Applying
that same shape here, named distinctly from PlanForge's existing "propose"
(= markdown → spec) to avoid vocabulary collision:

- **Propose (one pass, LLM where needed, otherwise deterministic diffing).**
  Given the compiled spec + the book's CURRENT real state (existing chapters,
  existing glossary entities/kinds, existing arcs — fetched live, not
  assumed), compute a structured diff of everything MISSING:
  `new_chapters` (from `package.chapters[]`, only ones without an existing
  real chapter — see the idempotency question in §4), `new_glossary_entities`
  (characters + mechanics/concepts, from the spec's own already-correct
  `glossary_seeds` — see [B] below), `new_glossary_kinds` (e.g. the spec's
  "Perfection_Addiction" mechanic doesn't map to any existing entity kind —
  propose a new PER-BOOK/PER-USER kind per the User Boundaries tenancy rule,
  never a System-tier write), `new_arcs` beyond what the book already has.
  **Exactly one LLM call for this whole diff, not one per proposed item.**
- **Persist as a record, not a transient response.** A new artifact/row (e.g.
  `plan_artifact` kind `"bootstrap_proposal"`) with `status: pending` and the
  full structured diff above. This is the "dry run" — nothing outside this
  record has been touched yet.
- **Human review, plain language, same "never touch raw JSON" principle as
  the Planner redesign mockup.** Surface the diff as readable cards (new
  chapters as a list of titles, new glossary entities as name+role, a new
  kind proposal explained in one sentence) — approve the whole batch, or
  (a later increment) approve/reject line-by-line. Rejecting requires a NEW
  propose pass (a fresh LLM call) if the user wants a revised plan — that's
  fine and expected; what must never happen is re-proposing automatically or
  silently on every apply retry.
- **Apply — deterministic, zero LLM calls.** Reads the `approved` record and
  performs the real mutations (book-service `createChapter` calls,
  glossary-service entity/kind POSTs) one item at a time, marking each as
  applied in the record as it goes (so a retried/resumed apply is naturally
  idempotent — skip anything already marked applied, per the idempotency
  question in §4). On any partial failure, the record's per-item status
  shows exactly what succeeded vs what still needs a retry — never a bare
  "500, try again" with no visibility into what already happened.

**[A] Create chapter shells (NEW, now behind the gate above).** The APPLY
step walks the approved `new_chapters` list and calls book-service's
`POST /v1/books/{id}/chapters` (currently unused by any planning code) to
create each real `Chapter` row; captures the returned `chapter_id`; persists
the `event_id ↔ chapter_id` mapping into the SAME bootstrap-proposal record
(under `applied_results`) so downstream steps and the GUI can resolve "this
planned scene is this real chapter." **This is the foundational bridge —
nothing else in this workflow can work without it, and it's the piece with
zero prior art to lean on** (no existing code creates chapters
programmatically today).

**[B] Seed glossary from the real spec (FIX, not new), also behind the
gate.** The APPLY step POSTs the already-computed, already-correct
`glossary_seeds` (`compile.py:12-34` — characters AND mechanics/concepts)
that today are silently discarded, REPLACING `propose_cast`'s spec-blind
re-derivation. This closes a real, separate bug found during this
investigation, independent of whether the rest of the auto-bootstrap
workflow ships — but note it now participates in the SAME review gate
(a human sees "these entities will be created" before they land), not a
silent side effect of compile() the way `propose_cast` is today.

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
steps at once. The two true unknowns — nothing in the codebase has ever done
either — are **(a) the propose→record→approve→apply gate mechanism itself**
and **(b) [A], chapter-shell creation**. [B]/[C]/[D] are either bug fixes to
existing code or wiring between two already-working pieces — real work, but
not architecturally novel the way (a) and (b) are.

**POC scope: the gate + [A], end to end. [B]/[ontology-kinds] included only
as a second proposal-item TYPE to prove the gate generalizes — not
necessarily wired to real glossary-service calls yet.**
- **Propose**: given a compiled `PlanningPackage` for a real arc (reuse the
  story-plan-v1 fixture / an existing `Ma Nữ Nghịch Thiên (POC)` book run),
  compute the diff against that book's REAL current chapters — one call,
  produces `new_chapters: [...]`. (Optionally also compute a trivial
  `new_glossary_entities` diff to prove the record shape generalizes beyond
  one item type, WITHOUT wiring the actual glossary POST yet — that's [B]'s
  own scoped pass.)
- **Record**: persist as a new `plan_artifact` kind `"bootstrap_proposal"`,
  `status: pending`, human-readable structured diff.
- **Review + approve**: minimal UI is fine for POC purposes (even a raw
  admin/debug view is acceptable to prove the mechanism — the Planner
  redesign mockup's "plain language" treatment can follow once the mechanism
  itself is proven) — but the APPROVE ACTION itself must be real (a genuine
  status transition on the record, not a hardcoded `True`).
- **Apply**: deterministic worker step reads the `approved` record, calls
  book-service's `createChapter` once per `new_chapters` entry, writes the
  resulting `chapter_id` back into the SAME record's `applied_results`,
  marks each item applied as it completes.
- **Verify live**: the created chapters actually appear in the Studio's
  Manuscript Navigator / Chapter Browser for that real book (not just a 200
  response) — same "verify by actually looking" discipline as the rest of
  this session's PlanForge work. Also verify: calling APPLY twice on an
  already-applied record is a safe no-op (the idempotency question below,
  actually tested, not just designed).
- Explicitly OUT of POC scope: the real [B] glossary POST wiring, [C]/[D]
  (drafting context + reachability), bulk auto-draft, line-by-line
  approve/reject (batch-only approve is fine for POC), the polished
  plain-language review UI. These become their own scoped PLAN/BUILD passes
  once the gate + [A] are proven, per this repo's "large effort → one
  continuous classified run, not five ad-hoc patches" guidance.

**Open questions for the next CLARIFY checkpoint before BUILD even on the
POC:**
1. Where does the bootstrap-proposal record live — a new `plan_artifact`
   kind (cheapest, matches existing patterns, reuses existing status-less
   artifact storage) or a new dedicated table with a real `status` column
   (more queryable, supports the approve/apply state machine more cleanly,
   more migration overhead)? Leaning dedicated table given the state machine
   (pending→approved→applying→applied/failed) is real workflow, not a static
   blob — but worth deciding explicitly, not defaulting silently.
2. Ordinal collisions — what happens if the book already has chapters (not
   truly empty) when chapter-shell creation runs? Append after the highest
   existing ordinal, or require an explicitly-empty book for POC purposes?
3. Idempotency — if PROPOSE is re-run for the same plan run (a real flow:
   propose → tweak → re-validate → re-compile → re-propose-bootstrap), does
   it diff against the LATEST real book state (so already-applied items from
   a prior approved record don't get proposed again), or against nothing
   (risking duplicate proposals)? The APPLY side's own idempotency (skip
   already-applied items within one record) is more straightforward; this
   cross-record idempotency question is the subtler one.
4. What does "reject" actually do to the record — deleted, or kept with
   `status: rejected` for audit/history (matching Enrichment's reversible-
   retract precedent of keeping a trail rather than deleting)?

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
- **Not** building a generic, reusable "proposal/approval engine" for other
  subsystems to plug into. This POC's record shape is scoped to bootstrap
  proposals only — generalizing it is a real future option (Enrichment's H0
  and this could plausibly converge someday) but inventing that abstraction
  now, before a second concrete consumer exists, is exactly the premature
  abstraction this repo's conventions warn against.
