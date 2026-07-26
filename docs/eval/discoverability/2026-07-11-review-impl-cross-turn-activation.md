# Review-impl — cross-turn activation fix + WS-5 / silent-success changes

**Date:** 2026-07-11. **Method:** 15-agent adversarial Workflow (5 reviewers × per-finding
verification), one reviewer per change area, each finding refuted-or-confirmed against the code.
**Scope:** the code shipped this session — the silent-success Go fix, the workflow-steering directive,
the two workflow seeds, the cross-turn activation mechanism fix, and the eval harness.

## Outcome: 7 findings, all MEDIUM/LOW, all fixed + verified. Core logic sound; no HIGH; no security issue.

| # | Sev | Area | Finding | Fix | Commit |
|---|---|---|---|---|---|
| 1 | MED | glossary | isError message pointed at `structuredContent` the chat agent loop **strips** — detail-less for non-unknown-kind failures | inline the distinct per-item reasons into the message text | `6581ae2bc` |
| 2 | LOW | glossary | message said "every item failed" even when some already existed | report real counts ("1 of 2 failed, 1 already existed") | `6581ae2bc` |
| 3+4 | MED | chat | auto-seed union leaked **stale curated find_tools accumulations** on a curated→auto flip (context-budget regression) | intersect the auto-union with **current-workflow** step tools; default = original hot-seed-only | `2fba9ad48` |
| 5 | MED | harness | a token-**minting** propose counted as effectful → suppressed the false-persistence hard-red | `_mints_confirm_token` excludes mints; confirms + draft-creates still count | `2fba9ad48` |
| 6 | MED | harness | per-movement thrash used a **global** `max_consec` | per-movement `max_consec` | `2fba9ad48` |
| 7 | MED | harness | a `commit_failed` bucketed as a successful resume | dedicated `commit_failed` hard-red | `2fba9ad48` |

## Notable

- **The review caught a real error in my own reasoning.** I'd claimed the auto-union was "a no-op except
  while a workflow is in flight." The reviewers showed that a session which was **curated earlier** (and
  accumulated find_tools/tool_load matches into `activated_tools`) then **flipped to auto** would leak
  those ad-hoc accumulations into the auto surface — up to ~6K tokens. The fix filters the union to the
  turn's currently-visible workflow step tools, with a safe default (no filter → original strict behavior),
  so neither the main path nor the resume path can leak.
- **Security re-confirmed, two ways.** Pre-checked by hand and independently by the security reviewer:
  chat-service `activated_tools` is **advertisement-only** (which schemas the model sees), not a
  permission gate. Advertising a Tier-W tool in auto mode cannot bypass write approval — the tier/RAID-C2
  confirm gate still fires on execution.
- **The harness findings mattered for eval integrity.** #5 could have masked the exact S06 false-"done"
  the harness exists to catch. After the fix, re-checked against the saved transcripts: S06 false-persist
  still fires (effectful=0, 2 claims), and S02's real draft-creates still count as effectful (3, 1).

## Verification

- **glossary:** 5 batch tests (2 new — inlined-reason + mixed-skip wording) + full api suite green.
- **chat-service:** full suite **1387** green; tool_surface/discovery **139** (3 new leak-drop tests);
  agent-registry api green.
- **harness:** targeted assertions for all 5 harness changes (mint-not-effectful, commit-failed hard-red,
  per-movement thrash) pass; original smoke green.
- **live:** S03 still drains **27→23** with `propose_merge`+`propose_status_change` across turns (the leak
  filter keeps the rail's tools); S02 ✅; S01 unchanged.

## Not fixed (out of scope / deliberate)

- The remaining S01 ~25% flakiness (model stalls before confirm) and the FE duplicate-card token wart are
  earlier, separately-tracked findings, not defects in this session's code.
