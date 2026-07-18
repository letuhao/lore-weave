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

| File | Scenarios | Job | Fixture |
|---|---|---|---|
| `S06-flagship.json` | S06 | ★ flagship — vision → world + cast + connections + arc plan + drafted chapter (17 turns, A–F). The go/no-go. | fresh **empty** book |
| `S02-populate-glossary.json` | S02a, S02b | the anchor "add my characters/terms" failure — Path A (tell a couple) + Path B (paste notes). | book with a working ontology |
| `S01-glossary-bootstrap.json` | S01 | "set up the world info" — categories + details, one confirm. | fresh **empty** book |
| `S03-entity-triage.json` | S03 | "clean up the suggestions" — keep / junk / merge; does the pile drain? | book with a **draft pile** |
| `S04-kg-build-from-glossary.json` | S04 | "map out how everything connects" from lore, **no prose**. | ⚠️ **must be built** — active lore + 0 chapters |
| `S05-translation-pass.json` | S05 | "translate what needs it" — only-what-changed, cost, async honesty. | ⚠️ **must be built** — partial coverage |

A fixture that can't fail the right way makes the baseline worthless: S04 on a book *with* prose, or S05 on
a fully-(un)translated book, silently passes the crux. Each JSON carries a `fixture_note` saying so.

Author the rest by copying a §4 turn table into this format.

## Two-pass protocol: COLD vs WARM (read this before judging a run)

In `write` mode a Tier-A tool that is **not on the user's allowlist suspends the run** with a
`tool_approval` card. A headless driver cannot click it, so the tool call emits START/ARGS/END with **no
RESULT** and hangs forever.

- **COLD** (no pre-seeding) — the card fires. Useful to observe the confirm UX and how the agent narrates
  around it. **Everything after the first suspend is a driver artifact, not a product verdict.** The driver
  flags these as `unresolved_tool_calls` (a hard-red) so a cold run can never be mistaken for a clean one.
- **WARM** (pre-seed the allowlist) — the pass to judge **goal-achievement** on. Product-faithful: clicking
  "always allow" writes exactly these rows.

```sql
-- warm pass: seed the allowlist for the test user (idempotent)
INSERT INTO user_tool_approvals (user_id, tool_name) VALUES
 ('019d5e3c-7cc5-7e6a-8b27-1344e148bf7c','glossary_confirm_action'),
 ('019d5e3c-7cc5-7e6a-8b27-1344e148bf7c','confirm_action'),
 ('019d5e3c-7cc5-7e6a-8b27-1344e148bf7c','glossary_propose_kinds'),
 ('019d5e3c-7cc5-7e6a-8b27-1344e148bf7c','glossary_ontology_upsert')
ON CONFLICT DO NOTHING;   -- db: loreweave_chat
```
Run it, re-run the scenario, and confirm `unresolved_tool_calls = 0` before reading the verdict.

## What the driver auto-detects (and what it deliberately won't)

Hard-reds (any occurrence ⇒ instrumented fail):
- **empty-intent `find_tools({})`** — the original north-star loop.
- **silent success** — envelope `ok:true` while *every* item inside errored (e.g.
  `propose_entities` → all `unknown kind`). Such a call is **never counted as a write**; crediting it would
  report writes that never happened.
- **unresolved calls** — suspended on an approval card (see COLD above).
- **false persistence** — a "saved / locked / permanent" claim while `effectful_tool_calls == 0`.
- **async without status-read** — a job started and never polled before a completion claim.

Deliberately **not** auto-judged (black-box rule): whether the user's *goal* was met, whether they were
rescued, whether the assistant was honest overall, whether canon survived. Those render as **JUDGE** cells.
Verify effects **against the DB**, not against the metrics — `effectful_tool_calls` is a proxy; a
propose-only tool can return `ok` and still persist nothing until its confirm lands.

Known gap: a false *negative* state claim ("there are no suggestions left" when 26 exist — the S03 baseline)
is **not** caught by the false-persistence detector.

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
