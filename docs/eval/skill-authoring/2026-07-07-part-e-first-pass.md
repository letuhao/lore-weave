# Skill quality-gate — Part E first pass (2026-07-07)

Spec: [`docs/specs/2026-07-07-skill-authoring-and-mcp-exposure-standard.md`](../../specs/2026-07-07-skill-authoring-and-mcp-exposure-standard.md) §8 (Part E). First live run of the skill eval loop against all 5 Part B skills (composition, translation, book, settings, jobs), driven by a new harness (`scripts/eval/run_skill_gate.py`) against the local `gemma-4-26b-a4b-qat` model, judged by 5 independent cold-start Agents (one per skill, absolute-scoring against each scenario's self-contained `ground_truth`, not A/B).

Raw transcripts: `docs/eval/skill-authoring/runs/sg-out/<skill>/transcript.jsonl`. Scenario sources: `scripts/eval/skill_scenarios/*.json` (37 scenarios, 41 turn-records, authored via 5 parallel fan-out agents against each skill's real MCP source).

## Headline result

**Zero hallucinated/invented tool names across all 37 scenarios.** The single highest-severity failure mode this entire skill-authoring effort exists to prevent — an agent inventing a plausible-sounding fake tool call (`settings_provider_create`, `book_share`, `jobs_resume`, etc.) when told a capability doesn't exist — never happened, even in the scenarios specifically designed to bait it (`settings_add_provider_key_no_invented_tool`, `sharing_collaborator_access_is_studio_ui_only`, `jobs_no_generic_resume_tool`). Every "what you genuinely cannot do here" section held.

## Aggregate scores

| Skill | Scenarios | PASS | FAIL | WEAK | NEEDS-RERUN |
|---|---|---|---|---|---|
| composition | 6 | 1 | 1 | 4 | 0 |
| translation | 7 | 1 | 3 | 1 | 2 |
| book | 10 (11 records) | 5 | 2 | 3 | 0 |
| settings | 8 | 5 | 1 | 1 | 2 |
| jobs | 6 | 1 | 0 | 5 | 0 |
| **Total** | **37** | **13** | **7** | **14** | **4** |

## A pre-existing, cross-cutting model/infra pattern — NOT a skill-content defect

Before trusting the FAIL/WEAK counts as skill-authoring signal, a control test was run: the SAME harness, against the already-shipped, previously-tested `glossary_skill` (not touched this session), with a structurally similar "check X before Y" prompt. It reproduced the identical failure signature — ~30 repeated `find_tools`/`glossary_search` calls, then an empty final `assistant` text. This confirms the dominant pattern seen across all 5 NEW skills too (long `find_tools` chains, 12-60 calls, that either end in empty text or a generic "having trouble accessing" apology) is a **pre-existing local-model/agent-loop characteristic**, not something introduced by this session's skill prose. It is NOT yet root-caused (candidates: `find_tools` search-relevance friction for these specific query phrasings, or `gemma-4-26b-a4b-qat`'s general persistence in multi-step tool loops — this repo's memory already documents this model's evals as noisy, `context-budget-test-model-gemma26b`: "estimator ±22%").

**Consequence for this pass:** no skill file was edited based on these results. Editing skill prose based on an n=1 run from a known-imprecise small local model would be pattern-matching noise, not signal — especially since the identical failure mode reproduces on an untouched, previously-validated skill. This is tracked as a new Deferred item (below), not silently fixed or silently ignored.

## Genuine content-level findings (the 7 FAILs, triaged)

Of the 7 FAILs, 5 share the "gave up searching, then falsely claimed the capability doesn't exist" shape (`list_configured_providers`, `new_chapter_first_save_may_use_base_version_one`, `bulk_create_reports_actual_created_and_skipped_counts`, `extraction_reasoning_effort_clamp_unknown`, `translation_job_status_not_generic_jobs_get`) — all downstream of the same cross-cutting discovery-persistence pattern above, not a skill-prose gap (each skill's own text correctly documents the tool the agent falsely denied).

**2 FAILs are a different, more interesting shape** — the agent DID reach a conclusion, and the conclusion contradicted a rule the skill states clearly:
- `cancel_job_irreversibility_warning` (translation) — the agent committed to canceling a job without surfacing the "cancel is terminal" warning `translation_skill.py`'s "Job control" section states explicitly.
- `motif_not_connected_to_planforge` (composition) — the agent claimed `plan_apply_revision` (a real tool) could "bake a motif into every arc of the plan" — a capability `composition_skill.py`'s "Motifs are NOT connected to PlanForge" line explicitly denies. Notably the tool NAME wasn't invented (unlike the pattern this whole effort was built to catch) — the agent invented a false CAPABILITY of a real tool instead, a related but distinct failure mode worth naming for future skill-authoring guidance.

These 2 are the closest thing to a genuine "the skill could state this more forcefully" signal — but with n=1 per scenario on a small local model, this is suggestive, not conclusive. Not acted on this pass (see Deferred).

## Deferred (per CLAUDE.md's defer-eligibility gate — both clear gate #2 "large/structural" and #4 "blocked/unresolvable now, needs investigation")

- **`D-SKILL-EVAL-DISCOVERY-LOOP-FLAKE`** — the cross-cutting `find_tools`-loop-then-give-up/silence pattern (14 WEAK + 4 NEEDS-RERUN + 5 of 7 FAILs across this run, reproduced independently on the pre-existing glossary skill). Needs its own investigation: is it `find_tools`' search relevance for certain phrasings, `gemma-4-26b-a4b-qat`'s tool-loop persistence specifically, or a `max_iterations`/loop-termination heuristic issue in `stream_service.py`'s tool loop. Root-cause before any skill-prose or agent-loop change — this run's data alone doesn't discriminate between those candidates.
- **`D-SKILL-EVAL-RERUN-AFTER-LOOP-FIX`** — once the above is root-caused/fixed, re-run this same harness (scenarios + driver already built and reusable) to get a cleaner signal on whether `cancel_job_irreversibility_warning` and `motif_not_connected_to_planforge` are real prose gaps or also loop-noise artifacts.

## Reuse

The harness (`scripts/eval/run_skill_gate.py`) and all 5 scenario files are reusable for any future skill (Phase 2+ per spec §5, or a re-run once the loop-flake is fixed) — point `QG_SCENARIOS` at a new `scripts/eval/skill_scenarios/<skill>.json` and set `SKILL_BOOK_ID`/`SKILL_PROJECT_ID` for a book-bound skill.
