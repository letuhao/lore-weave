# Architecture v1 retirement — final report

**Date:** 2026-09-03 · **Branch:** `feat/frontend-tools-mcp-migration` · **Verdict:** `v1 IS DEAD`

Reproduce every claim below:

```
python scripts/v1_retire/runstate.py            # the board (D1..D8)
python scripts/v1_retire/runstate.py --check    # exit 0 iff v1 is dead
python scripts/v1_retire/gates.py --selftest    # every gate proven red-able
python scripts/v1_retire/gates.py               # G1..G6 against the repo
```

All four exit `0`.

---

## 1. What v1 actually was

The premise this work started from was that v1 carried ~199 tools. **It carried three:**
`confirm_action`, `glossary_confirm_action`, `glossary_propose_entity_edit`. The 199 figure came
from my own first classification script, which used ONE sentinel for both "absent from the
catalogue" and "has no `visibility` key" — and since live rows carry no such key, every live tool
looked absent. Corrected before any work was planned on it.

**The three tools were never the target. Their chat-service-local IMPLEMENTATION was.** All three
still exist, still federate, and still render the same cards.

---

## 2. The board

| | Clause | Proven by |
|---|---|---|
| D1 | the construct is gone | `frontend_tools.py` does not exist |
| D2 | nothing chat-service-local reaches the model | all 3 resolve from the federated catalogue |
| D3 | the manifest declaration's owner is a domain service | no served tool row owned by chat-service |
| D4 | the tasks gate is total where a task is possible | 17 cited exemptions, 0 uncited bare mints |
| D5 | deprecated is dead to the model UNAIDED | live probe: `tool_load` refuses + names the successor |
| D6 | no document describes v1 as current | 0 docs leave the deleted module looking live |
| D7 | regression is impossible, not merely unlikely | G1..G6 green AND all 6 proven red-able |
| D8 | every service this loop touched still IMPORTS | pytest collection per service |

**D5, D6 and D7 did not exist until the end of this run.** The board implemented D1–D4 and exited
`0` — green over three unimplemented definition-of-done clauses. It had also numbered the import
check "D5", colliding with the spec's own D5. Renumbered to D8; the three real clauses implemented.

Suites, all full, never a subset: chat-service **3881**, composition **3988**, knowledge **4327**,
translation **1196**, python kit **1031**, ai-gateway **286**, and `go test ./...` green for
book-service, glossary-service and the Go kit.

---

## 3. Decisions I took without asking (DQ-V6)

The instruction was *investigate and decide yourself; I will review the final report.* Every
decision, with the evidence that drove it.

### 3.1 Overturning an owner ruling — DQ-V9 vs DQ-V5

**DQ-V5 ruled:** the two confirms become glossary-service MCP tools.
**I did not do that.** A domain MCP tool has a **server executor** — the model calls it and the
server acts. These three tools exist to make a *human* act. Giving them a server executor would
let the model confirm its own action, deleting the gate the tools are for. All three became
ai-gateway **directive** tools instead (GATE-2 class (d), "no server executor"): validate, return
a directive, the browser gates on the human.

This is the one place I overrode an explicit ruling. It is a safety inversion, not a preference.

### 3.2 SDK promotion

- **Python `PgTaskStore` added to the kit but NOT exported from `__init__.py`.** That module
  imports its submodules eagerly, so exporting it would put `asyncpg` on the import path of every
  kit consumer, most of which never touch Postgres.
- **Go: a `pgstore` SUBPACKAGE, not the kit root.** Go has no lazy import. Measured before
  choosing: every Go service depending on `loreweave_mcp` already depends on `pgx`, so no consumer
  gains a dependency it lacked.
- **`PG_TASK_STORE_DDL` promoted with the code**, so the schema cannot drift from its reader.
- **The promotion nearly shipped the WORSE copy.** I picked book-service's store because it was
  the original. Glossary's carried a fix book's lacked: on an expired task it explains the TTL
  lapsed instead of returning a bare `ErrTaskNotWaiting`. Both services *compiled* against the
  book-only version, so nothing failed. Merged as the superset. **A promotion must carry the
  superset — picking "the original" is picking by provenance, not by content.**

### 3.3 Gate totality (D4)

- **17 exemptions, each citing code**, keyed on `file::symbol`. The registry was first keyed on
  `file:line`; inserting one resolver shifted every line below it and six exemptions silently
  stopped matching — the census jumped 6→11 while still reporting "exempt: 2". A key that any
  unrelated edit moves is a registry that empties itself.
- **`plan_bootstrap_apply` gated with re-authorization**; translation-service's four effects
  extracted and gated (DQ-V2, no exemption taken).
- **The census was keyed on one spelling and missed a whole service.** It matched
  `mint_confirm_token` / `MintConfirmToken` only; knowledge-service mints with its own
  `mint_action_token` and has no task gate at all. D4 could have reported PASS over it.

### 3.4 Documentation

- **`test_frontend_tool_validation.py` retired** after verifying all 44 of its cases exist in
  ai-gateway specs — counted, not assumed.
- **The manifest row was removed, not edited** (`LIFECYCLE_MOVES` has no `admitted → admitted`
  edge, so a change of owner is a new admission, not a mutation).
- **AGENTS.md's tool count became a pointer, not a new number.** It read "316 tools" and was stale
  within the same day, because this loop itself added three. A corrected number drifts again; the
  deriving command does not.
- **10 decision records got a redirect banner; 3 live-guidance docs got their prose corrected
  instead.** A decision record that cites `frontend_tools.py` is evidence, and rewriting it
  destroys what it is evidence of. AGENTS.md and the two standards docs are not records — they
  were telling readers the deleted module was the schema home, and were simply wrong.

### 3.5 Rulings I deliberately did NOT execute

- **DQ-V1 (rename `frontend-tools.contract.json`).** 40+ files reference it, nearly all dated
  records that must not be rewritten. Renaming would turn every historical citation into a
  dangling path — strictly worse for de-rot than the name is. The *ownership* half of the ruling
  was applied: the standards docs now name ai-gateway as the owner.
- **DQ-V4 (rename the synthesised batch card to `batch_confirm`).** The frontend renders that card
  by **coalescing** pending `confirm_action` records, not by a distinct name. Renaming the backend
  half alone would drop it out of `FRONTEND_TOOLS` and **delete the Tier-A injection-damage cap
  card** — a safety mechanism. It needs paired frontend work, and the synthetic suspend is never
  advertised to the model, so it does not block v1's retirement.

---

## 4. Defects this run found in its own work

**A regression I shipped, then caught.** `glossary_confirm_action` was given the *same* directive
marker as `confirm_action`. chat-service maps marker → suspend name, so every glossary confirm
began suspending as `confirm_action`. The main chat UI accepts either name and was unaffected;
`cms-frontend`'s admin transcript gates on exactly `tc.tool === 'glossary_confirm_action'` and has
no auto-confirm fallback, so its confirm card silently became a 10px grey text line. TypeScript
cannot see it — the name crosses the wire as a string. Fixed at the source (its own marker), not
by patching the consumer, because the invariant the whole move was justified by is *the tool's
HOME changed; its IDENTITY did not*.

**The test that should have caught it was green.** `confirm-tools.spec.ts` asserted the directive
types are distinct — over three CONSTANTS, which are trivially distinct from one another. There
are four gated tools. The assertion's population was the markers, not the tools, so the one thing
that could go wrong sat outside it. Re-based on tools; both halves now go red on the original
defect, verified by re-injecting it.

**A footgun the migration created.** `WRITE_FRONTEND_CONTRACT=1 pytest` — the regeneration command
three docs instructed — regenerated the contract from `frontend_tools.py`. That module is deleted,
so the generator's only remaining input was a **frozen test copy**. Editing a schema in
ai-gateway, updating the contract, then "regenerating" as documented would have silently reverted
the contract to retired v1 shapes, and the only test that could catch it lives in another service.
The write path now raises and names ai-gateway as the owner.

**`find_tools`'s test asserted a retired tool still worked** — red at HEAD for eight days, in a
suite nobody could get to green. Verified pre-existing by running it against HEAD's own files
(restore md5-checked). Rewritten to assert the retirement, including that the refusal names the
replacement rather than returning an empty result a caller would read as "no such capability".

**Four live tools were steering the model at dropped tools.** Measured over the 202 live tools:
`book_structure_edit`, `composition_list_canon_rules`, `glossary_confirm_action`,
`glossary_ontology_delete`. Two had declared successors and were re-pointed; two named capabilities
with **no live replacement**, and the honest repair was to say so — a description that stays silent
about a missing capability is the one that gets hallucinated around. New gate:
`scripts/test_a_live_tool_never_sends_the_model_to_a_dropped_one.py`, which accepts a retired tool
named *as* retired and still rejects one the text tells the model to call.

---

## 5. My own measurement errors, and what they cost

| Error | Consequence | Correction |
|---|---|---|
| One sentinel for two answers | 199 live tools looked absent | two distinct returns; premise fixed before planning |
| `grep ... \| head -6` | "consumer" false positives filled the window, so provider-registry was recorded ledger-free | re-read untruncated; it has `consumeSettingsToken` |
| `str(Path)` on Windows | `"/tests/" in s` never matched — 28 sites against a true 14 | `as_posix()` |
| Exemptions keyed on `file:line` | 6 exemptions silently stopped matching | keyed on the enclosing symbol |
| G3 read a key the census never returns | **gate vacuously green over 17 sites** — and its selftest agreed, because I had fed it a shape the real caller never produces | selftest now passes the shape `_gate_census()` actually returns |
| Ran `vitest` on a `jest` suite | 17 files "failed" — my invocation, not the code | `npm test` |
| Created a falsifier file during a running `--check` | that run exited 1 on my own seed | re-ran clean; never mutate under a live verification |
| Two substring detectors matched their own fix | G6 reported 8 findings, 0 of them defects — one was the correction quoting the defect it fixed | claim-vs-mention: strip quoted spans, exclude conditionals |

The last row is the recurring one. **A word-search over prose finds the repair as readily as the
defect**, and this repo has shipped three guards that were green with the fix deleted.

---

## 6. What is NOT done

1. **V2 — the gate's wire rate is unmeasured.** D4 proves totality in the SOURCE. Proving zero
   bare `confirm_token`s on the wire needs a live run; none was taken (no paid run without an
   explicit yes and a stated call count).
2. **The catalogue cache is a snapshot of the DEPLOYED catalogue.** The four description fixes are
   in source; they reach the model only after the services rebuild and
   `scripts/refresh_tool_catalog_cache.py` runs. The new gate correctly reports 4 until then — it
   is reporting deployment truth, not a stale reading.
3. **DQ-V1 and DQ-V4** — deliberately not executed, reasons in §3.5. Both need a decision to close
   or drop.
4. **Nothing is committed.** The branch carries this work uncommitted.
