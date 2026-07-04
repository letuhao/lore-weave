# T5 grounding intent-gate — CORRECTED report (audit, 2026-07-04)

**Supersedes `T5-2026-07-04.md`, whose conclusion was WRONG.** The session self-audit
(3 cold-start reviewers) found the original A/B was confounded AND the feature had a
production no-op bug. This records the corrected findings + the honest measurement state.

## What was wrong with the original finding

The original report concluded "token-saving redundant / thesis weakened" and I raised a
"T3 optional" decision-point on it. Both were **invalid**:

1. **Production no-op bug (reviewer HIGH-1):** the gate fed `session.project_id` (a
   KNOWLEDGE project id) to glossary's `book_id`-keyed known-entities route → always
   `[]` → `grounding_needed=True` every turn → the gate was **byte-identical to disabled**.
2. **Confounded A/B:** the Dracula *book* (`019eeb09`) had **no knowledge project**, so
   `build_context` → `ProjectNotFound` → grounding degraded (`memory_knowledge.total=0`)
   in BOTH arms. The knob changed nothing because there was nothing to skip.
3. **Misattributed the 28K→120K split:** it is NOT grounding. The lore turn called MCP
   tools (`glossary_search`, `book_list`×2) — a multi-pass tool loop — and `input_tokens`
   is the SUMMED input across passes: the **~41K MCP tool-schema catalog re-sent each
   pass**. The real per-turn lever here is the tool catalog, a different tier than T5.

## Fixes applied (committed this session)

- `33a954036` — the gate now resolves project→`book_id` (new knowledge route
  `/internal/context/project-book/{id}` + cached `knowledge_client.resolve_book_id`),
  so it queries known-entities with the real book id. Multilingual bias-to-include
  (CJK/VN open; role-noun/thematic questions open; meta/capability questions stay
  gated out). Widened the entity vocab (min_freq=1, limit=500).
- `b6ef10ba6` — two live-caught false-positives: em-dash `—` no longer reads as
  non-English (require a non-ASCII *letter*); a junk 1-char entity `'i'` no longer
  `\b`-matches "I'm" (drop <3-char ASCII tokens).

## Live validation — the gate now FIRES correctly

Against a Dracula-linked knowledge project (`019f2be0`), gemma-4-26b, per-turn
`entity_presence` decisions:

| Turn | tag | gate | reason |
|---|---|---|---|
| smalltalk "what can you help me with" | no_lore | **gated OUT** | meta_question |
| status "give me a 3-step plan" | status_op | **gated OUT** | no_entity_no_anaphora |
| "who is the main character of this book" | lore_recall | open | lore_intent |
| "tell me about the core conflict" | continuity | open | lore_intent |
| "now make it darker — keep the same character" | continuity | open | anaphora |
| "how does the MC change across chapters" | cross_chapter | open | lore_intent |

✅ **The gate is no longer a no-op** — it makes correct, sensible per-turn decisions.
This is the primary audit corrective, live-proven.

## The honest measurement state (token SAVINGS still not quantified)

A meaningful savings A/B needs **full-mode grounding** (extraction-enabled project with
passages): only then does `grounding=True` (full, expensive) differ from `grounding=False`
(static, cheap). An extraction-DISABLED project uses static mode for BOTH, so the gate
saves 0 by construction.

Seeding full-mode grounding is a **multi-step pipeline** with real prerequisite gates:
create project ✅ → set embedding model ✅ → **pass the embedding golden-set benchmark
(`kg_run_benchmark`)** ⛔ (blocks extraction dispatch: `409 benchmark_missing`) → dispatch
extraction → workers ingest passages → measure. This is buildable (the tools exist) but
it is a genuine pipeline run, not a quick step.

**Evidence-backed interim conclusion:** the gate is correct + safe + now firing, but its
savings are BOUNDED by `build_context`'s share of the turn, and every run shows that share
is small next to the **41K MCP tool-schema catalog** re-sent across tool-loop passes on
lore turns. The likely bigger Context-Budget win is **tool-catalog / discovery trimming**,
not grounding gating — but that is a hypothesis to measure, not a new confident claim.

## Next (to finish "measure honestly")
Run `kg_run_benchmark` for the embedding model → dispatch a 2-chapter Dracula extraction →
re-run the gate ON vs OFF A/B (`T5_INTENT_GATE_ENABLED`) → the delta on a no-lore turn IS
the gate's real savings. Then decide validate-or-kill on data. (A heavier pipeline run;
can go in the background.)
