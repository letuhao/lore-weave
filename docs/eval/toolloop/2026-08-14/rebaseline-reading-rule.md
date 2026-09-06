# How the re-baseline will be read — committed BEFORE the batch runs

Written while `c2-final` was still in flight and `scenarios-rebaseline.json` had not been launched,
so the reading cannot be fitted to the result. The DATA bar already refuses a falsifier edited after
the run it judges; the same standard applies to how a 200-run batch is graded.

## What is being measured

The 40 still-blocked tools outside cycle 2, re-run at K=5 with the `agentSurface` event kept.
36 seed assertions preflighted clean against the live schema first — that check exists because one
typo once cost a whole 25-run batch.

## The pre-registered expectations

**13 tools carry a recorded `surfaced 0/N`**, and every one of them is ANSWERABLE today against its
own prompt. Those figures predate cycle 1's 37 declaration widenings and nobody re-measured them:

`translation_patch_block`, `memory_timeline`, `glossary_create_chapter_link`,
`glossary_create_evidence`, `jobs_cancel`, `jobs_pause`, `kg_ontology_propose`,
`registry_set_skill_enabled`, `glossary_deep_research`, `kg_triage_schema_write`,
`composition_motif_bind_edit`, `jobs_get`, `glossary_book_sync_apply`

> **I expect most of these to surface.** If they do, the honest reading is *the ledger was stale*,
> not *this batch fixed them* — nothing was shipped for most of them.

**6 tools are reached by the refusal-arming shipped this cycle**, verified against the deployed
builder rather than assumed: `jobs_cancel`, `jobs_get`, `jobs_pause`, `kg_propose_edge`,
`plan_bootstrap_apply`, `kg_triage_schema_write`. None was cycle 2's target.

## What would REFUTE the claims this batch rests on

- **If a tool recorded `0/N` still surfaces 0/5** — then answerability is not what puts it on the
  wire, and the sweep that called 46 of 48 "answerable" does not mean what I said it means.
- **If P4-PRECONDITION's six surfacing rows all surface and still cannot be exercised** — then they
  are fixture problems after all, and my claim that "a tool that never reached the wire was never
  blocked by its fixture" was the wrong inference for them.
- **If the 6 armed tools show the supplier advertised and never called** — that cell was empty
  across 35 runs in cycle 2, and one instance here would put the model-behaviour reading back.

## What this batch CANNOT do

It concludes nothing by itself. Each tool still has to pass its own four bars through `gate.py`, and
LIVE-clean needs a run free of the provider flake measured at 1.7% per run — over 200 runs, expect
roughly 3. A tool failing only on that is not a finding about the tool.
