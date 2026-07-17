# PlanForge — propose reads the existing manuscript (D-PLANFORGE-PROPOSE-BLIND)

> **Status:** ✅ **BUILT + QC'd (2026-07-17).** PO lifted the Q-35-OQ5 seal ("build PROPOSE-BLIND and
> QC it") — the seal read *"needs a PO to own it"*, and the PO did. Built in 5 phases (§6), all
> committed; live-smoked end-to-end + adversarially reviewed. **Shipped with the deploy ceiling OFF**
> (`PLANFORGE_GROUND_ON_EXISTING_ALLOWED=false`) — the richer grounding is dark until the A/B eval
> (§6 P5) proves it improves the plan, then the ceiling flips. See the BUILD CLOSE-OUT at the end.
>
> Commits: P1 `ac0026856` (gather lens) · P2 `38952a21d` (rules merge) · P3 `a7065246a` (LLM/async
> prompt) · P4 `5596e7e05` (setting+ceiling+wiring) · P5 `39cfbaff1` (planner copy-switch) · QC
> `9a8cbacd6` (MCP agent-parity).
>
> **This revision (2026-07-17):** upgraded from high-level design + 3 open PO questions to a
> **build-ready** design — every read grounded in an existing seam, a concrete `ExistingState` schema,
> the budget model wired to the real `enforce_budget` allocator, the migration, the merge-not-duplicate
> algorithm, the per-path prompt diffs, the A/B rollout gate, and a phased build plan. **The 3 open
> questions were PO-APPROVED 2026-07-17 (§4) — now sealed decisions.** The design is COMPLETE; nothing
> further to specify. Only the seal (Q-35-OQ5) stands between it and a build.

## 1 · The problem

`PlanForge.propose` generates a `NovelSystemSpec` (arcs, cast, variables, beats) from **only** the
pasted braindump. It is **blind to the book's existing manuscript**: proposing a plan for a book with
200 written chapters ignores every one of them and re-invents arcs/characters that already exist.

Grounded in code (Q-35-OQ5 evidence):
- `propose_spec(doc)` (`engine/plan_forge/propose.py`) takes only the parsed braindump.
- `propose_spec_llm(raw_path, …)` (`engine/plan_forge/propose_llm.py`) takes only a raw file path.
- `propose_spec_llm_async(...)` (`engine/plan_forge/propose_llm_async.py`, driven by
  `worker/operations.py:run_plan_forge_propose`) — the async worker path, same blindness.
- `PlanRunCreate` (`routers/plan_forge.py`) carries `source_markdown / mode / model_ref / force /
  genre_tags` — the `book_id` is grant-gated but **never read for state**.

So a returning author gets a plan that contradicts their own book — a **generation-quality defect**,
not a GUI gap (which is why it is out of scope for the GUI-parity waves and needs its own track).

## 2 · Why it's a real track, not a quick edit

The proposer has **three entry paths** that must all change together, or the fix is inconsistent:
1. the **rules** path (`propose_spec`) — deterministic transcriber, no LLM,
2. the **2-step LLM** path (`propose_spec_llm` → analyze → materialize → normalize),
3. the **async worker** path (`propose_spec_llm_async`).

Plus the **run schema** (`PlanRunCreate` + the `plan_run` row) must record what existing-state was
folded in (for reproducibility + so a re-propose is deterministic). This is a prompt/contract change
across the three proposer surfaces + the run schema + a new gather lens — a serious plan, per the
defer gate (gate #2 large/structural).

## 3 · Design

### 3.0 What already exists (so the build COMPOSES, never re-derives)
Every read the gather lens needs already has a seam — this is the key finding that makes it buildable
without new cross-service infrastructure:

| existing-state component | existing read to reuse | proof it exists |
|---|---|---|
| **arcs / structure** | `StructureRepo(pool).list_tree(book_id)` → filter `kind=="arc"` → `title`, `summary` | `_rules_preflight` (`plan_forge_service.py:334-339`) already reads exactly this and dedupes by `lower(strip(title))` |
| **cast** | `KALClient` → `GET /internal/books/{id}/entities` (`clients/kal_client.py`) — the keyset-paged read of the book's FULL entity roster (the Knowledge Access Layer that superseded the old `GlossaryClient.list_entities`), filtered to character kinds | the KAL already exposes this book-scoped, grant-safe, paged character read; `_bind_roster` resolves names against the seed roster, but existing-state needs the book's persisted glossary — that is the KAL |
| **manuscript spine** | `OutlineRepo.linked_chapter_nodes(book_id)` (`db/repositories/outline.py:305`) → chapter nodes with `title` + `synopsis` + `story_order`; take the last-N by `story_order` | that method already returns the book's chapter outline nodes; F-6 verification confirmed chapters materialise here (`kind='chapter'`) |
| **variables / motifs in play** | `self._runs.latest_artifact(book_id, run_id, "package" \| "motif_plan")` | already the freshness-input read in `_serialize_run` / `pass_status` |
| **budget trim** | `app/packer/budget.py::enforce_budget(segments, budget, counter)` — priority ladder, drop-lowest-first | the Context Budget Law allocator, already shipped |

**No new cross-service client, no new table, no new provider call.** The gather lens is an
orchestration over reads that all exist today (the "missing infrastructure is unbuilt work, not
blocked" rule — here it turns out there is almost no unbuilt infrastructure at all).

### 3.1 A book-state "gather lens" (the one genuinely new piece)
`gather_existing_state(book_id, *, budget: ExistingStateBudget) -> ExistingState` — a summary-shaped,
hard-capped read (the `composition_package_tree` philosophy: orientation, not content). Lives in a new
`engine/plan_forge/existing_state.py`, injected the repos/clients it composes (testable in isolation).

**`ExistingState` schema (the typed contract):**
> **Build-time correction (2026-07-17, verified against `kal_client.py`):** `KalClient.roster()`
> returns only `{entity_id, name}` — it does NOT expose role/trait or a mention-frequency rank. So the
> cast component carries `{name, glossary_entity_id}` and is capped by COUNT (first-K, drained order),
> not mention-rank; `notes["cast"]` reports "showing K of N". Richer cast fields (role/trait/mention
> rank) would need a richer glossary endpoint — a future enhancement, out of scope for this track. The
> anti-re-invention goal only needs the existing NAMES + their entity ids, which the roster provides.

```python
@dataclass
class CastMember:      # from the KAL roster (name + entity id — all the roster exposes)
    name: str
    glossary_entity_id: str

@dataclass
class ArcSummary:      # from StructureRepo.list_tree
    title: str
    one_line: str      # summary, truncated

@dataclass
class ChapterBrief:    # from OutlineRepo, newest-first
    story_order: int
    title: str
    synopsis: str      # one-line, truncated

@dataclass
class ExistingState:
    chapter_count: int                 # ABSOLUTE — never trimmed (the "how far along" signal)
    recent_chapters: list[ChapterBrief]  # last-N, the continuation point
    cast: list[CastMember]             # ranked, capped
    arcs: list[ArcSummary]
    variables: list[str]               # variable codes/names already in play
    motifs: list[str]                  # motif labels already adopted
    #: PER-COMPONENT provenance so the prompt + UI can say what was folded in AND what was trimmed.
    #: Absent signals are ABSENT-WITH-A-NOTE, never zeros (silent-success law): e.g. notes["cast"] =
    #: "42 characters, showing top 20 by mention" or "no glossary characters yet".
    notes: dict[str, str]
    #: The reproducibility fingerprint — which chapters/arcs/cast were folded in (sorted ids +
    #: chapter_count), hashed. Recorded on the run so a re-propose with the same book state is
    #: deterministic and the freshness model can reason about it.
    grounded_fingerprint: str
    def is_empty(self) -> bool:  # cold-start ⇒ the flag is a no-op, scenario-1 keeps working
        return self.chapter_count == 0 and not self.cast and not self.arcs
```

**Ranking + capping (so a 500-entity / 200-chapter book fits the budget):**
- **cast** ranked by mention-count / chapter-span (the glossary already tracks mention frequency),
  keep the top-K within budget.
- **recent_chapters** = the last N by `story_order` (the recent state the plan must *continue from* —
  the front of the book is context the author already knows; the tail is where they are).
- `chapter_count` is reported ABSOLUTELY and is never trimmed — it is the single most important "how
  far along is this book" signal and costs ~3 tokens.

### 3.2 The budget model (resolves OQ-3) — reuse `enforce_budget`, do NOT write a new allocator
Model each component as `packer.budget.Segment`s with a priority ladder, then call the existing
`enforce_budget(segments, budget, counter)`. Recommended ladder + soft caps (percent of the
`ExistingStateBudget.total`, itself a slice of the plan-orientation budget from the Context Budget
Law):

| component | priority (higher = kept longer) | soft cap | rationale |
|---|---|---|---|
| `chapter_count` scalar | `PROTECTED` | ~3 tok | the continuation anchor; never drop |
| `recent_chapters` (last N) | 90 | 40% | where the story IS — the plan continues from here |
| `cast` (top-K by mention) | 80 | 35% | who already exists — the #1 re-invention risk |
| `arcs` | 60 | 15% | structure already committed |
| `variables` + `motifs` | 40 | 10% | in-play systems; softest, trimmed first |

`enforce_budget` drops lowest-priority segments first when over budget and returns `over_budget` if the
protected anchor alone exceeds it (it never will at ~3 tokens). The soft caps are pre-trim ceilings per
component; `enforce_budget` is the final global trim. **OQ-3 is thereby resolved by reuse** — no new
allocator, the split is a priority assignment the PO can tune, and the Context Budget Law owns the
`total`.

### 3.3 Thread it through the three paths
A single new prompt fragment, `existing_state_prompt(state: ExistingState) -> str`, rendered into an
"EXISTING STATE — continue and do NOT re-invent these" section. Wired per path:

- **Rules path (`propose_spec`)** — the rules mode is a *transcriber*, so it does not prompt an LLM;
  instead it **merges-not-duplicates** deterministically (see 3.4). `propose_spec` gains an optional
  `existing: ExistingState | None`; when present it post-processes the parsed arcs to drop/annotate
  ones that title-match an existing arc, reusing the SAME `lower(strip(title))` key
  `_rules_preflight` already uses.
- **2-step LLM path (`propose_spec_llm`)** — `analyze_user_prompt(markdown, existing=...)` and
  `materialize_user_prompt(analyze_json, checksum, existing=...)` gain the EXISTING STATE section. The
  ARC COVERAGE rule (already highest-priority in both `ANALYZE_SYSTEM`/`MATERIALIZE_SYSTEM`) gains a
  sibling **CONTINUITY rule**: *"characters/arcs already in EXISTING STATE must be REFERENCED by their
  existing name/title, never re-invented under a new name."*
- **Async worker path (`propose_spec_llm_async`)** — same prompt builders (they are shared); the op
  (`run_plan_forge_propose`) calls `gather_existing_state` before invoking the client and passes the
  state through.

### 3.4 Merge-not-duplicate (rules path) — reuse the preflight key
The rules path already has the collision detector (`_rules_preflight`, P-O1a): it compares proposed arc
titles against existing arc titles by `lower(strip(title))`. Promote that key into a shared helper and
use it in `propose_spec`'s post-processing:
- a proposed arc whose title-key matches an existing arc → **annotate** it (`continues_existing: true`,
  keep the id stable) rather than mint a duplicate node,
- a proposed cast name that matches an existing glossary character (case-folded) → carry the existing
  `glossary_entity_id` so the later roster-bind resolves to the SAME entity, not a new one.
This makes the rules path consistent with the LLM path's prompt instruction, deterministically.

### 3.5 The run schema + reproducibility
- `PlanRunCreate` gains `ground_on_existing: bool = <deploy-gated default>` (see OQ-2). Declared
  explicitly on the Pydantic model (never rely on `extra='ignore'` — the `rest-write-mirror-drops-
  fields` bug), enum/bool-validated on write.
- `plan_run` gains a `grounded_on JSONB NULL` column recording `{fingerprint, chapter_count,
  arc_ids[], cast_entity_ids[], trimmed: {...}}` — what was folded in. A re-propose with the same book
  state produces the same fingerprint → deterministic; the freshness model can compare it. Migration:
  additive `ADD COLUMN ... NULL` (no backfill needed — null = "not grounded", the honest default for
  historical runs). Follows the `add-column-if-not-exists-never-revisits-a-bad-default` caution: the
  default is deliberately NULL, not a value we might regret.

### 3.6 Interaction with the honesty copy (the SET-8 consumed-by-effect rule)
When `ground_on_existing` is ON **and** the gather returned real state, the planner replaces the
honesty copy with a positive affirmation built FROM `ExistingState.notes` (*"Grounded on 42 chapters +
20 cast members (top 20 of 42 by mention); 3 existing arcs continued."*). When off / cold start, the
current honesty copy stands. The copy is CONSUMED-and-proven-by-effect (it renders the actual folded-in
counts, never a stored blob) — the SET-8 rule, and the same "surface the effective value + its source"
discipline the settings standard mandates.

## 4 · Decisions (PO-APPROVED 2026-07-17 — SEALED; do not re-litigate)

> These were the three open questions; the PO approved the recommended resolutions on 2026-07-17.
> They are now **sealed decisions** — a future builder implements them, does not re-open them (per the
> "re-read a sealed decision, don't re-litigate" rule). Change requires an explicit PO reversal.

- **OQ-1 · owning track → composition-service, PlanForge-v2 compiler track. ✅ APPROVED.** Rationale:
  every read is composition-local or an existing internal client (arcs via `StructureRepo`, cast via the
  KAL `/internal/books/{id}/entities`, spine via `OutlineRepo.linked_chapter_nodes`, motifs/vars via
  `latest_artifact`). No new service boundary. Opens when the PlanForge v2 compiler track next re-opens
  (Q-35-OQ5's target trigger).
- **OQ-2 · default `ground_on_existing` → FALSE at ship, flipped to TRUE org-wide only after the A/B
  eval passes. ✅ APPROVED.** This is the SET-boundary-correct answer: `ground_on_existing` is a **per-user
  setting** (two authors genuinely want different values — a continuation-writer wants it on, a
  fresh-spinoff author wants it off), with a **deploy ceiling** (`PLANFORGE_GROUND_ON_EXISTING_ALLOWED`,
  default OFF at ship) so `effective = AND(deploy_allows, user_enables)`. A behavior-changing default
  **fails closed** (the `spend-causing-setting-fails-closed` rule) until the eval proves grounding
  improves the plan; then the ceiling flips ON and the per-user default becomes TRUE. Never a global
  `*_ENABLED` env flag standing in for the per-user choice (that would be a `/review-impl` finding).
- **OQ-3 · budget split → resolved by reuse (§3.2). ✅ APPROVED.** No new allocator: `enforce_budget` +
  the priority ladder above, with the `total` owned by the Context Budget Law's plan-orientation
  allocation. The percentages are PO-tunable soft caps, not hard-coded behavior.

**Spec status after approval:** with all three decisions sealed, this design is **COMPLETE and
build-ready** — nothing further to specify. The only thing between here and code is the *seal lifting*
(the PlanForge-v2 track re-opening, Q-35-OQ5). A builder can start at §6 P1 without re-opening any
design question.

## 5 · Acceptance criteria
1. Proposing for a book with existing arcs/cast **does not duplicate** an existing arc by title, and
   the generated cast **references** existing characters (carries their `glossary_entity_id`) rather
   than re-inventing them — a live smoke on a seeded multi-chapter book, diffing the proposed spec
   against the book's glossary + structure tree.
2. The gather lens is **budget-bounded** — a 500-entity / 200-chapter book's `ExistingState` stays
   under the token cap (assert `counter(render(state)) <= budget.total`); `notes` reports what was
   trimmed (no silent truncation).
3. A **cold-start** book (no chapters) yields `ExistingState.is_empty()` and proposes exactly as today
   (scenario-1 regression, byte-identical spec for the same braindump).
4. `ground_on_existing=false` reproduces today's braindump-only behavior (the escape hatch), and the
   deploy ceiling OFF forces false regardless of the user setting (`effective = AND(...)` proven).
5. The planner UI shows the grounded affirmation (with real folded-in counts) when state was folded in,
   the honesty copy otherwise — proven by EFFECT (browser smoke), not by a stored flag.
6. `plan_run.grounded_on` records the fingerprint; a re-propose with unchanged book state produces the
   same fingerprint (determinism).

## 6 · Phased build plan (when the track opens)
- **P1 — gather lens, isolated.** `existing_state.py` + `ExistingState` + `gather_existing_state`
  composing the existing reads, with the `enforce_budget` trim. Unit-tested against seeded repos
  (cold-start empty, 500-entity cap, notes-on-trim). No proposer wiring yet — pure, testable.
- **P2 — rules path merge-not-duplicate.** Promote the preflight title-key to a shared helper; wire
  `propose_spec(existing=...)`; deterministic dedupe tests.
- **P3 — LLM + async paths.** `existing_state_prompt` + the CONTINUITY rule in the shared prompt
  builders; wire both `propose_spec_llm` and `propose_spec_llm_async`; live smoke a real gemma propose
  on a seeded book, diff against glossary.
- **P4 — schema + setting.** `PlanRunCreate.ground_on_existing`, the deploy ceiling, `plan_run
  .grounded_on` migration, the per-user setting (server-side, effective-value+source surfaced).
- **P5 — UI copy switch + A/B eval.** The grounded-affirmation vs honesty-copy switch (consumed by
  effect); run the A/B eval (canon-check-judge harness) comparing grounded vs blind proposals on
  seeded multi-chapter books; only on a positive result flip the deploy ceiling ON + the per-user
  default to TRUE.

## 7 · Effort / risk
L–XL: a new gather lens + prompt/contract changes across 3 proposer paths + the run schema + the UI
copy switch. Risk is **generation quality** (does grounding actually improve the plan?) — gated behind
the P5 A/B eval before defaulting on. **No user-facing tenancy change** — the gather lens reads only
grant-gated book state the caller already has EDIT on (the propose route is already `_gate_book(...,
EDIT)`); it adds no new read surface a user couldn't already reach.

---

## BUILD CLOSE-OUT (2026-07-17)

**Built (P1–P5 + QC), all committed:**
- **P1** gather lens `existing_state.py` (arcs=StructureRepo · cast=KAL roster · spine=OutlineRepo
  `recent_chapter_briefs` · systems=caller package · budget-trim=`enforce_budget`), degrade-safe,
  deterministic fingerprint. 7 unit tests.
- **P2** rules merge-not-duplicate (`merge_existing_into_spec` + shared `title_key`, preflight refactored
  to it). 6 tests.
- **P3** LLM+async EXISTING STATE prompt block + CONTINUITY rule (beside ARC COVERAGE) + deterministic
  merge backstop. 4 tests.
- **P4** `PlanRunCreate.ground_on_existing` + deploy ceiling (`settings.planforge_ground_on_existing_allowed`,
  default OFF, effective=AND, fails-closed) + `_gather_book_state` wiring (rules→propose_spec(existing);
  LLM→prepend block, superseding the arc-only `_ground_llm_source`) + `plan_run.grounded_on` migration.
  7 tests.
- **P5** planner "Continue this book" toggle + the honesty-copy↔grounded-affirmation switch (SET-8,
  proven by effect) + 18-locale i18n. 3 tests.
- **QC** MCP `plan_propose_spec` agent-parity (the review found the agent couldn't ground; fixed).

**Live-smoke (real gateway→composition, ceiling ON):** a grounded rules-propose recorded `grounded_on`
(fingerprint + 3 arcs + 2 cast + 9 chapters + notes) and merge-annotated a re-declared arc
`continues_existing=true` / a new arc `=false`; a blind propose left `grounded_on` null (fails closed);
the LLM path prepended the EXISTING STATE block into the enqueued job. BE 487 + FE 83 green.

**Coverage gaps — the 2026-07-17 follow-up cleared them (PO: "clear the gaps + measure for real"):**
1. ✅ **Per-user setting persisted (OQ-2)** — the planner toggle now loads from + writes through to
   `/v1/me/preferences` (`planner.groundOnExisting`), server-side, one home. Commit `bf4b5afc8`.
2. ✅ **Systems populate live** — `_gather_book_state` reads the book's latest `spec` (variables) +
   `motif_plan` (motifs) via a new book-scoped `latest_artifact_for_book`. Commit `cce54ad81`; a live
   ambiguous-`id` SQL 500 (JOIN) that the unit suite couldn't see was caught by the measurement + fixed
   (`bcafc99f4`); proven live ("4 variable(s) in play").
3. 🔵 **Cast name+id only — assessed, legitimate cross-service defer.** The KAL roster is DELIBERATELY
   projection-restricted to `{entity_id, name}` (`kal-read.controller.ts:107`); adding role/kind is a
   knowledge-gateway (TS) change to a deliberate restriction, out of composition scope. The
   anti-re-invention goal only needs names, which are present.
4. ✅ **A/B eval RUN (đo thật) — and it says KEEP THE CEILING OFF.** Two blind-vs-grounded gemma proposes
   on book 019f6555: cast continuity **0/3 in every cell (TIE)**; grounding added nothing (arc continuity
   3/3 is the baseline `_ground_llm_source`, not a win). Root cause: a character-less braindump generates
   no cast → normalize pads "Nữ chính"; prompt grounding references but does not INVENT a cast. Per OQ-2
   the ceiling therefore does **not** flip — the eval gated a generation-quality claim that isn't real.
   Report + follow-ups: `docs/reports/2026-07-17-propose-blind-ab-eval.md`. Commit `6597a1ee2`.
