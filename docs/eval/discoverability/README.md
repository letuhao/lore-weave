# Discoverability & workflow live-test runs

Live-test transcripts + findings for the scenarios in
[`docs/specs/2026-07-09-agent-discoverability-and-workflow/scenarios/`](../../specs/2026-07-09-agent-discoverability-and-workflow/scenarios/).

One file per run: `YYYY-MM-DD-<scenario>-<model>.md`. Each records the black-box user verdict **plus** the
instrumented evidence (discovery-call count, empty-intent `find_tools` count, false-"done" count,
canon-fact retention, wall-clock, compaction survival). For the flagship (S06), use a **per-movement
checkpoint table** (A–F × {goal-achieved · no-rescue · no-thrash · honest · canon-intact}), not a single
end verdict — see S06 §11.

Model under test: `gemma-4-26b-a4b-qat` (mid-tier local). Conventions (model_ref resolution, two-pass
cold/warm, logging) live in the scenarios folder README and S06 §11.
