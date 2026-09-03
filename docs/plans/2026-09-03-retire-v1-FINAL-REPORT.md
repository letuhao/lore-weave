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

### 3.5 Two rulings I deferred, argued against, and then executed

I recommended against DQ-V1 and was overruled. Recording both the objection and the outcome,
because a report that quietly drops an argument it lost is not a record of what happened.

- **DQ-V1 — `frontend-tools.contract.json` is now `browser-tools.contract.json`.** My objection:
  125 files reference the old path, and 97 of them are dated records I must not rewrite, so a
  rename leaves those citations dangling. The counter-argument is the stronger one: "frontend
  tool" named a construct that no longer exists — a tool chat-service INTERCEPTED — and a contract
  whose name asserts a dead owner is exactly the rot this work removes. 28 live references
  updated; the 97 dated ones are served by `contracts/RENAMES.md`, a rename map so an old citation
  still resolves. That mitigation only holds if the next rename lands there too.
- **DQ-V4 — the Tier-A cap gate suspends as `batch_confirm`.** Done with its frontend half in the
  same change, which was the whole risk: the FE renders that card by COALESCING pending
  `confirm_action` records, so a backend-only rename would have dropped it out of `FRONTEND_TOOLS`
  and deleted the Tier-A injection-damage cap card outright. It is worth doing because the two
  concepts were told apart by "the `confirm_token` is empty" — a property of the payload standing
  in for an identity. `frontend/src/features/chat/components/__tests__/batchConfirmIdentity.test.ts`
  pins it, and was proven red by removing the name from `FRONTEND_TOOLS`.

  That guard caught a defect in ITSELF first: its membership helper scanned the array literal
  including comments, and the comments quote tool names while explaining the rename — so a name
  mentioned only in prose would have counted as live. Comments are stripped now. A test written to
  catch a substring trap had the substring trap.

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

## 6. Deployment — the gap that mattered most

**The board said `v1 IS DEAD` while the running system still ran v1.** Every clause of D1–D8 was
true of the source and of the suites, and none of it was true of the thing serving traffic:

| Service | State when the board first read green |
|---|---|
| chat-service | `frontend_tools.py` still in the image, `browser_tools.py` absent, `generic_frontend_tool_def` still referenced — the v1 fallback firing every turn |
| ai-gateway | had `confirm-tools.js`, but predated the identity fix, so the glossary confirm still shared a marker |
| translation-service | no `DESC_JOB_RESUME`; the gate work was not there at all |

A source board cannot see a deployment, and nothing in the definition of done required it to.
Every changed service was rebuilt and redeployed, then verified from inside the container by a
property of the whole file rather than the symbol I added.

`scripts/v1_retire/live_probe.py` now measures on the running stack what the board can only prove
in source. All four pass, and they are idempotent:

| Probe | What it asks the live system |
|---|---|
| P1 federation | the three KIND-C tools are served, and `served_by: ai-gateway` — read from the live catalogue, not the snapshot |
| P2 gate negotiation | **V2** — the same call answers a tasks-capable client with a durable task and a non-capable one with a `confirm_token` |
| P3 steering | no live tool's model-facing text sends the model at a tool the superseded gate drops |
| P4 advertised on the wire | every name in `chat_messages.advertised_tools` resolves federated, or sits on the measured consumer-local list |

Two of them found real defects on their first run, which is the argument for their existence:

- **P3 caught a repair I had reported as complete.** `composition_list_canon_rules` carried the
  same sentence TWICE — once as the tool's `description`, once as an argument annotation. I fixed
  the annotation, saw the gate still red, and attributed it to catalogue-cache lag. It was not
  lag; it was the half I had not fixed. *A gate that stays red after your fix is telling you
  something; explaining it away is how the fix ships incomplete.*
- **P4 found the allowlist could not do its job.** `conversation_search` and
  `chat_search_sessions` are advertised and not federated. Both are legitimate — they read
  chat-service's OWN conversation store, which is categorically different from v1's sin of
  serving another domain's schema locally — but `CONSUMER_LOCAL_OK` never named them. D2 passed
  only because it checked three names by hand, so it could not have distinguished a real
  regression from a chat-native tool. The list is now measured, not guessed.

P4's first version also carried its own copy of that allowlist and immediately disagreed with the
real one — a second home for a fact, inside the loop whose subject is one home per fact. It
imports now.

---

## 7. What is NOT done

1. ~~The frontend is built from a different branch.~~ **That was wrong, and it was wrong in a
   way worth naming.** I ran `docker inspect` on `lw-iso-frontend-1` because its name contained
   "frontend", found it built from a second checkout on another branch, and reported that the app
   was served from code this branch does not control. It is not: `infra-frontend-1` serves
   :5174 — the port the harness had been driving all along — and is built from THIS repo's
   `infra/docker-compose.yml`. `lw-iso-frontend-1` sits on :25174 and is a different stack
   entirely.

   **I inspected the container whose NAME matched instead of the one serving the traffic**, then
   built a conclusion about branch boundaries on top of it. The check that would have caught it
   in one step is the one I had already used twice that day: ask which container publishes the
   port, not which container sounds right. Both frontends are rebuilt from this branch.

2. **One durable task sits in `input_required`** on the throwaway probe book, by design — it is
   P2's evidence. It is on a `ZZ Throwaway` book, never the dogfood book.
3. **The live run used one model and one turn** for P4's population. The probes are deterministic
   at the MCP boundary; the chat-path half is a single real turn, so P4's 54 advertise passes are
   a floor on coverage, not a survey of every surface the app can build.
