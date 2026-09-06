# Contract renames — a map, so an old citation still resolves

A contract file is cited by **records**: plans, specs, run-states and decision sheets that were
written when a path was true. Those documents must not be rewritten — a decision record is
evidence, and editing its lines destroys what it is evidence of. But a reader who greps a record's
path and finds nothing concludes the contract was deleted, which is worse than a stale name.

So a rename lands here, and the old path stays findable.

| Old path | New path | When | Why |
|---|---|---|---|
| `contracts/frontend-tools.contract.json` | `contracts/browser-tools.contract.json` | 2026-09-03 | DQ-V1, architecture-v1 retirement |

## The 2026-09-03 rename, in full

**Nothing about the file's CONTENT changed.** Same schemas, same keys, still the single
cross-language source of truth. Only the name moved.

"Frontend tool" named a construct that no longer exists: a tool **chat-service intercepted** and
handed to the browser. That interception is deleted — `chat-service/app/services/frontend_tools.py`
is gone. What survived is the other question the old name confused with it: **which tools does the
BROWSER execute?** Those tools have no server executor, so a person acts and the browser performs
the effect. The codebase now says that in one vocabulary:

  * `services/chat-service/app/services/browser_tools.py` — `BROWSER_EXECUTED_NAMES`,
    `is_browser_executed`
  * `contracts/browser-tools.contract.json` — their arg schemas
  * `services/ai-gateway/src/mcp/` — `confirm-tools.ts`, `propose-edit-tool.ts`, `ui-tools.ts`,
    each read against that contract by its own spec

**One name for one concept.** The old name asserted an owner (chat-service's frontend tooling)
that no longer owns anything, which is the exact rot the retirement existed to remove.

### What this rename cost, recorded honestly

28 live references were updated — code, tests, scripts and the standards docs. **97 dated records
still cite the old path** and were deliberately left alone. That is why this file exists.

I recommended against the rename for that reason and was overruled; the reasoning on both sides is
in [`docs/plans/2026-09-03-retire-v1-FINAL-REPORT.md`](../docs/plans/2026-09-03-retire-v1-FINAL-REPORT.md).
The table above is the mitigation, and it is cheap — but it only works if the next rename lands
here too.

### Regenerating the contract

There is no generator. `WRITE_FRONTEND_CONTRACT=1` used to rebuild it from `frontend_tools.py`;
with that module deleted its only remaining input was a frozen test copy, so it would have
overwritten this contract with retired v1 shapes. It now raises. **Edit the JSON by hand**, then
update the ai-gateway TS and the FE resolver — ai-gateway's specs go red if the three disagree.
