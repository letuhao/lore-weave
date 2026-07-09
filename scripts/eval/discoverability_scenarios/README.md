# Discoverability scenario JSONs (Track C · WS-7)

Reusable black-box scenario inputs for
[`../run_discoverability_scenario.py`](../run_discoverability_scenario.py). One JSON per
scenario (`S0x` ↔ umbrella `W0x`), authored **verbatim from the user turns** in
[`docs/specs/2026-07-09-agent-discoverability-and-workflow/scenarios/`](../../../docs/specs/2026-07-09-agent-discoverability-and-workflow/scenarios/).

The driver runs these against the real chat agent, drains each turn over SSE, and emits a
baseline / re-test report the **same way every time** — so `❌ baseline → ✅ re-test` is an
apples-to-apples comparison. It hits the chat-service HTTP/SSE surface (the backend agent loop
where the `find_tools` thrash lives), which is reproducible; frontend-**tool** scenarios still
need a live browser smoke as their final gate (agent-gui-loop lesson).

## Black-box rule (why the JSON has no tool names)

A scenario is the **user's own words** only. The harness measures *how* the agent behaved
(§10 evidence: empty-intent `find_tools`, discovery-call counts, thrash, async honesty, jargon
candidates) but never decides whether the user's **goal** was met — that is judged from the
observable outcome. In the generated report, instrumented rows are auto-filled; the
`goal-achieved / no-rescue / honest / canon-intact` cells are marked **JUDGE**.

## Format

```jsonc
{
  "scenario": "S06",                  // id (or use {"scenarios":[...]} for multi)
  "title": "...",
  "maps_to": "W06 vision-to-book",
  "persona": "...",
  "permission_mode": "write",          // "ask" for read-only journeys
  "context": {"book_context": {"book_id": "<BOOK_ID>"}},   // or null
  "enabled_skills": [],                // usually [] — a naive user pins nothing
  "canon_facts": ["fiancé identity", ...],   // S06 §10 8-fact retention checklist (judge)
  "jargon_denylist": ["kind","entity","ontology", ...],    // §1 words that must never be required
  "movements": [{"id":"A","label":"Here's my idea"}, ...], // for the §11 checkpoint table
  "turns": [{"movement":"A","user":"..."}, ...]            // one user utterance per turn
}
```

- `<BOOK_ID>` / `<PROJECT_ID>` / `<CHAPTER_ID>` in `context` are substituted from
  `SKILL_BOOK_ID` / `SKILL_PROJECT_ID` / `SKILL_CHAPTER_ID` env — the JSON stays account-agnostic.
- `turns` may be plain strings or `{"movement","user"}` objects. Movement tags drive the
  per-movement checkpoint table + TTFUO.
- `jargon_denylist` should mirror the scenario's §1 "words I do NOT know" list.

## Scenarios here

| File | Scenarios | Job |
|---|---|---|
| `S06-flagship.json` | S06 | ★ flagship — vision → world + cast + connections + arc plan + drafted chapter (17 turns, movements A–F). The go/no-go. |
| `S02-populate-glossary.json` | S02a, S02b | the anchor "add my characters/terms" failure — Path A (tell a couple) + Path B (paste notes). |

Author the rest (S01, S03, S04, S05, …) by copying a §4 turn table into this format.

## Run (in-container — same pattern as `run_skill_gate.py`)

```bash
# 1. resolve gemma's model_ref (user_default_models is empty for the test acct):
#    SELECT user_model_id, alias, capability_flags FROM user_models
#     WHERE owner_user_id='019d5e3c-7cc5-7e6a-8b27-1344e148bf7c' AND is_active;
#    -> the gemma-4-26b-a4b-qat chat UUID

# 2. copy driver + scenario into the chat-service container
docker cp scripts/eval/run_discoverability_scenario.py infra-chat-service-1:/tmp/ds.py
docker cp scripts/eval/discoverability_scenarios/S06-flagship.json infra-chat-service-1:/tmp/scen.json

# 3. run (QG_KEEP_SESSIONS=1 so you can pull tool_calls JSONB afterward)
docker exec \
  -e QG_RUN_LABEL=2026-07-09-S06-baseline \
  -e QG_MODEL_REF=<gemma_uuid> \
  -e SKILL_BOOK_ID=<fresh_empty_book_id> \
  -e QG_SCENARIOS=/tmp/scen.json -e QG_OUT=/tmp/ds-out \
  -e QG_KEEP_SESSIONS=1 -e QG_REPORT_DATE=2026-07-09 \
  infra-chat-service-1 python /tmp/ds.py

# 4. pull the reports out to the eval folder
docker cp infra-chat-service-1:/tmp/ds-out ./docs/eval/discoverability/runs/
```

Output per scenario in `QG_OUT/<label>/`: `<id>-report.md` (the §7 baseline + §11 checkpoint
table), `<id>-transcript.jsonl` (every turn: user · assistant · full tool calls with args ·
budget), `<id>-metrics.json`.

**Preconditions:** LM Studio up with gemma loaded (`lms` reload on a mid-stream wedge); rebuild
stale images before smoking (else false-green); for S06 use a **fresh empty** book id.
