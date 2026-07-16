# PlanForge — propose reads the existing manuscript (D-PLANFORGE-PROPOSE-BLIND)

> **Status:** detail spec (design) for a FUTURE track. **NOT built, and MUST NOT be built inside
> Wave 5 / S3** — the wave-5 adjudication (Q-35-OQ5) sealed this: *"Wave 5 must NOT touch it… a
> generation-quality redesign, not a GUI gap, and no wave owns it."* Writing this design doc is
> planning, not touching the engine — it does not violate the seal. S3 shipped only the **honesty
> copy** ("Proposed from this braindump only. Existing chapters are not read.") as the interim
> truth-telling. This spec is what eventually replaces that copy with the real capability.

## 1 · The problem

`PlanForge.propose` generates a `NovelSystemSpec` (arcs, cast, variables, beats) from **only** the
pasted braindump. It is **blind to the book's existing manuscript**: proposing a plan for a book with
200 written chapters ignores every one of them and re-invents arcs/characters that already exist.

Grounded in code (Q-35-OQ5 evidence):
- `propose_spec(doc)` (`engine/plan_forge/propose.py`) takes only the parsed braindump.
- `propose_spec_llm(raw_path, …)` (`engine/plan_forge/propose_llm.py`) takes only a raw file path.
- `PlanRunCreate` (`routers/plan_forge.py`) carries `source_markdown / mode / model_ref / force /
  genre_tags` — the `book_id` is grant-gated but **never read for state**.

So a returning author gets a plan that contradicts their own book — a **generation-quality defect**,
not a GUI gap (which is why it is out of scope for the GUI-parity waves and needs its own track).

## 2 · Why it's a real track, not a quick edit

The proposer has **three entry paths** that must all change together, or the fix is inconsistent:
1. the **rules** path (`propose_spec`),
2. the **2-step LLM** path (`propose_spec_llm` → ground → normalize),
3. the **async worker** path (`propose_llm_async`).

Plus the **run schema** (`PlanRunCreate` + the `plan_run` row) must record what existing-state was
folded in (for reproducibility + so a re-propose is deterministic). This is a prompt/contract change
across four surfaces + a new gather lens — a serious plan, per the defer gate.

## 3 · Design

### 3.1 A book-state "gather lens" (the new, reusable piece)
`gather_existing_state(book_id, *, budget) -> ExistingState` — a summary-shaped, hard-capped read (the
`composition_package_tree` philosophy: orientation, not content). It composes EXISTING reads (do not
re-derive):
- **arcs / structure** — from the spec tree (arc titles + one-line each).
- **cast** — from glossary (character entities: name, role/kind, a one-line trait), capped + ranked by
  mention/chapter-span so a 500-entity book fits the budget.
- **manuscript spine** — chapter count + the last-N chapter one-line synopses (the recent state the
  plan must continue from), via the manuscript navigator's existing summaries.
- **variables / motifs already in play** — from the latest compiled package / motif plan, if any.

It returns a **bounded** structure (token-budgeted, per the Context Budget Law) — never the full
manuscript. Absent signals are ABSENT-with-a-note, never zeros (silent-success law).

### 3.2 Thread it through the three paths
- Add an optional `existing_state: ExistingState | None` argument to `propose_spec` /
  `propose_spec_llm` / the async op. When present, the prompt gains an "EXISTING STATE — continue and
  do NOT re-invent these" section; the rules path uses it to *merge-not-duplicate* arcs by title
  (the same dedupe the P-O1a pre-flight already does for compile).
- `PlanRunCreate` gains `ground_on_existing: bool = true` (a per-run choice — SET boundary: two
  authors want different values; a cold-start book naturally yields an empty ExistingState, so the
  flag is a no-op there, keeping scenario-1 working).
- `plan_run` records a `grounded_on` fingerprint (which chapters/arcs were folded in) so a re-propose
  with the same inputs is deterministic and the freshness model can reason about it.

### 3.3 Interaction with the honesty copy
When `ground_on_existing` is on AND the gather returned real state, the planner replaces the honesty
copy with a positive affirmation ("Grounded on N existing chapters + M cast members"). When off / cold
start, the current honesty copy stands. The copy is CONSUMED-and-proven-by-effect (never a stored
blob) — the SET-8 rule.

## 4 · Acceptance criteria
1. Proposing for a book with existing arcs/cast **does not duplicate** an existing arc by title, and
   the generated cast **references** existing characters rather than re-inventing them (a live smoke
   on a seeded multi-chapter book, diffing the proposed spec against the book's glossary).
2. The gather lens is **budget-bounded** — a 500-entity / 200-chapter book stays under the token cap
   (assert the ExistingState size).
3. A **cold-start** book (no chapters) still proposes exactly as today (scenario-1 regression).
4. `ground_on_existing=false` reproduces today's braindump-only behavior (the escape hatch).
5. The planner UI shows the grounded affirmation when state was folded in, the honesty copy otherwise.

## 5 · Open questions for the PO
- **OQ-1:** which track owns this? (It is cross-cutting: composition-service engine + glossary reads +
  the planner UI copy. Suggest it opens when the PlanForge v2 compiler track next re-opens, per
  Q-35-OQ5's target trigger.)
- **OQ-2:** default `ground_on_existing` **true** or **false**? (Spec leans **true** — the blind
  default is the bug; but true changes behavior for every returning author, so it is a PO call.)
- **OQ-3:** budget split between cast vs manuscript-spine vs arcs in the gather lens (needs the
  Context Budget Law's allocator — coordinate with that track).

## 6 · Effort / risk
L–XL: a new gather lens + prompt/contract changes across 3 proposer paths + the run schema + the UI
copy switch. Risk is **generation quality** (does grounding actually improve the plan?) — gate the
rollout behind an A/B eval (the canon-check-judge harness) before defaulting it on. No user-facing
tenancy change (the gather lens reads only grant-gated book state).
