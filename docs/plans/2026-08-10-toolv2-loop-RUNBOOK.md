# TOOL-V2 LOOP — one tool, one full development cycle

**Status:** open 2026-08-10 · **SSOT for progress:** `contracts/agent-runtime-toolv2-ledger.json`,
written only through `scripts/toolv2-loop.py --record`.

**PO's definition, and it is the whole point:**

> *"1 loop hoàn chỉnh là 1 qui trình phát triển 1 tool v2 giống như mọi qui trình phát triển module
> khác, 1 tool được xem là 1 feature, không phải chỉ có chuyển qua là xong."*
>
> convert → **run and prove it** → failed ⇒ investigate and fix the architecture or the backend,
> across services if that is where the defect is → run again → **proven ends the iteration**;
> still broken ⇒ the tool is **skipped with a reason** and the loop moves to the next one.

---

## 🔴 The correction that produced this design, recorded because it was mine

I first scoped the loop as *"convert what already has evidence (84 tools) and record the other 235
as having no subject."* That treats **evidence as something only history can provide.** The loop
**makes** evidence — it runs the tool. A tool with no recorded traffic is therefore not out of
scope; it merely arrives without a free reproducer.

What survives from that measurement is the **order**, not the exclusion:

| population | tools | what it means for an iteration |
|---|---|---|
| called and **never** succeeded | **34** | a reproducer already exists in the corpus — the iteration starts at *investigate* |
| has recorded successes | 84 (12 admitted) | a shape can be verified against real results before anything is run |
| never called | 201 | the first invocation has to be **constructed** before anything can be proven |

---

## The six phases of one iteration

**1 · PICK** — `python scripts/toolv2-loop.py --next`. The queue is derived from the catalogue and
the live corpus, never typed. Take the top row; the reason is printed beside it.

**2 · INVESTIGATE** — before touching code. What does this tool actually fail on, measured on its
own recorded calls? Split the population; do not trust the aggregate. **This phase has produced
every real finding in CP-5**, and skipping it is how a member gets built for a subject that turns
out to be something else.

**3 · CONVERT** — author the contract against what phase 2 measured. Rules already paid for:

* the `output_contract` shape comes from the **union of every recorded success with a stated `n`**,
  never from the tool's description (measured: description-authored shapes were wrong **4 of 5**)
  and never from one sampled result (**two tools are polymorphic** and one sample named one arm as
  the whole contract);
* a member with no subject **is not written** (§7) — that rule has already withdrawn one spec row
  and one of my own questions;
* promote through `scripts/agentruntime-admit.py --promote`, which is the only path to `admitted`.

**4 · PROVE** — a real turn, real service, real boundary, on a **throwaway book**. Deploy first
(`docker compose build` + `--force-recreate`) and verify the contracts are byte-identical
in-container: **the manifest in the repo is not the manifest on the wire**, and that has caught a
silently-absent registry once already.

**5 · FIX** — if the run fails, the defect is fair game **wherever it lives**: chat-service, the
owning service, the gateway, or the contract itself. Cross-service is explicitly in scope. Re-run
phase 4 after the fix.

**6 · CONCLUDE** — exactly one of:

* `--state proven` — a live run succeeded, with the session id as evidence. **The iteration ends.**
* `--state blocked` — investigated, and it cannot be made to work now. The note must say **what was
  tried and what would unblock it**. The iteration also ends, honestly.

**A blocked tool is a finished iteration, never a silent skip.** The loop stops when every tool is
`proven` or `blocked` — not when every tool is converted.

---

## Rules this loop inherits, each already paid for

* **Every denominator from the SSOT or live data. Never typed** — including the queue.
* **Verify the deployed image matches source before diagnosing.** A stale image cost a full
  investigation once.
* **A content-creating live run uses a throwaway book.** Smoke debris in the dogfood book reads as
  a product bug later.
* **Run the whole suite before claiming green.** A `-k` subset hid 12 failures for a day.
* **Every new guard needs a falsifier that reds it**, or a recorded reason why no edit can.
* **A repair that emits parseable-but-wrong output needs a post-condition.** Disguised ≠ repaired.
* **Prose is not the lever.** Three separate defects had a correct, complete, actionable message and
  failed anyway (101 placeholder ids, 88 unknown kinds, 266 missing arguments). If the proposed fix
  is a better sentence, it is not a fix.

---

## Deferred questions — recorded when they block, cleared by evidence, never by guessing

A question that blocks the CURRENT tool does not stop the loop and does not get invented an answer.
It lands here with its evidence, and the loop moves on. These are revisited when the catalogue has
no remaining independently-executable work, or when new evidence makes one of them live.

### DQ-1 · An explicit JSON `null` for an OPTIONAL string is rejected before the handler runs

*Raised by:* iteration 1 (`glossary_propose_curation`, phase 2) · *Measured:* 2 calls / 1 session —
the tool's only genuine failures that are **not** the singular/plural conflation.

```
{"op":"status_change","status":"active","book_id":null,   "entity_ids":["019fea5a-…"]}
{"op":"status_change","status":"active","winner_id":null, "entity_ids":["019fea5a-…"]}
→ validating "arguments": … /properties/book_id: type: … has type "null", want "string"
```

Go's `json:"…,omitempty"` makes a field optional in the *struct*, but the generated JSON Schema
still says `type: "string"`, so the MCP SDK's validator refuses `null` before any of our code sees
it. Sending `null` for "I have no value" is an ordinary thing for a model to do, and `winner_id`
here is a field of a **different op** — the flat superset invites filling it in with a blank.

**The question, and it is a product/architecture call, not a lookup:** should every optional string
on the glossary MCP surface accept an explicit `null` (`type: ["string","null"]`)? That is a
schema-generator change across *every* glossary tool, and this runtime has already had one
whole-provider de-federation caused by a schema-type edit. **2 measured calls do not justify that
blast radius**, and no amount of local reasoning settles it — so it is recorded, not guessed.
*Would clear it:* a corpus sweep showing the pattern is broad, or an explicit decision to accept it.

### DQ-2 · Five glossary-service DB tests are red against the live `loreweave_glossary`

*Raised by:* iteration 1, phase 4 · *Confirmed **pre-existing** at HEAD `b334fe531`* by re-running
them in a detached worktree — they are not this iteration's regression, and the fix was not allowed
to hide behind them.

`TestTriggerStillFiresOnWatchedFields` (short_description / deleted_at / permanently_deleted_at),
`TestTriggerSkipsRecalcOnUpdatedAtOnly`, `TestK2aSearchVectorRefreshesOnDirectShortDescriptionWrite`,
`TestK3_AutoRegenOnDescriptionUpdate` — all "recalc did not fire", i.e. a **snapshot-recalc trigger
that is absent or disabled in that database**. Plus `TestSyncTool_AvailableApplyRoundTrip`
("fresh adopt: want 0 updates, got 3"), which is shared-state pollution: the test asserts a clean
adopt against a DB that already has three adoptable standards.

Whether these are a real trigger regression or environment drift is **not decidable from the test
output alone** — and this runtime has already spent a full investigation on host-env drift wearing
a code bug's clothes. *Would clear it:* comparing the trigger definitions in `loreweave_glossary`
against the migration chain.

### DQ-3 · `kg_propose_edge` cannot satisfy its own precondition, and INV-K1 says it may not

*Raised by:* iteration 2 · *Measured:* 2 calls / 2 sessions — the only genuine failures the tool
has, once the 14 human denials and 1 pending card are removed from its 17.

Both were refused `KG_ENDPOINT_NOT_NODE`: an edge whose endpoints are not yet graph nodes. The
message is already correct, complete, and names the remedy tool by name
(`kg_project_entities_to_nodes`) — so **a better sentence is not available as a fix**. One of the
two sessions did then call the projection successfully and **never retried the edge**; the other
never projected at all.

The obvious repair — have `kg_propose_edge` project the missing endpoints itself — is **forbidden
by INV-K1**: this tool must never write Neo4j, which is why it parks a proposal for a human instead.
Its own source says so at the precheck (*"This READS Neo4j … the write stays human-gated"*).

**The question:** is a two-call round trip the intended cost of INV-K1, or should the runtime chain
the projection on `KG_ENDPOINT_NOT_NODE`? Chaining is a mechanism built for a 2-call population,
which §7 says is not a subject; weakening INV-K1 is a safety decision that is not mine.
*Would clear it:* traffic after the tool is actually reachable — the corpus cannot say how often
this bites, because the tool has never been permitted to run.

### DQ-4 · A resumed turn OVERWRITES its own first pass's tool calls

*Raised by:* iteration 3 · *Observed directly*, not inferred: session
`019fec80-…-e004` held three rows at `sequence_num 2` — `glossary_search` (done),
`glossary_get_entity` (done), `glossary_propose_entity_edit` (deferred). After the resume it held
**one**. The upsert does `tool_calls = EXCLUDED.tool_calls`, a straight overwrite, and a resumed
turn builds a fresh `tool_calls_history`, so the first pass's calls are gone.

**This corrupts the loop's own evidence, in a direction that flatters nothing and misleads
everything.** Every suspension a human ACTUALLY CAME BACK TO has its `deferred` row erased by the
resume; only the abandoned ones survive to be counted. So §1's *"38 of 41 deferred calls sit in
turns the human never returned to"* is very likely an artefact of this, not a finding about users.

The corpus is consistent with that and **cannot measure the size of it**, which is the worst
property a data loss can have. 53 `deferred` rows survive across 6 tools (42 of them
`glossary_propose_curation`); the resumed ones left no row to count, so the loss is invisible
rather than merely large. The denominator here is not under-reported — it does not exist.
It also means the reads that produced a call's arguments vanish from the record whenever the call
suspended — which is exactly the sequence iteration 3 needed to see.

**Why it is recorded and not fixed here:** the fix is a MERGE rather than an overwrite, and this
row is upserted several times per turn *and* across turns. The file's own comment says both
previous merge strategies for the sibling segment columns were wrong in opposite directions
(*"COALESCE erased the resumed turn's earlier passes, and the concatenation that fixed it
duplicated every pass a checkpoint had already written"*), which is why `segment_merge_sql` exists
and is interpolated at both upsert sites. `tool_calls` needs the same treatment and the same
dedupe-by-id care, and doing it badly silently duplicates or deletes recorded calls.
*Would clear it:* an id-keyed merge with a test that a resumed turn keeps its first pass, both
upsert sites covered.

---

## Debt this loop surfaced but did not absorb

Recorded here rather than fixed inline, because the loop's whole design is one tool at a time and
a run that absorbs every adjacent finding never reaches its second row.

### D-1 · Five falsifiers do not red the guard they name

Found by a **clean** `agentruntime-falsification.py --run` (332 of 337 red; the 5 below report
*"GREEN — the guard requires nothing"*). All five predate this loop; every new guard added in
iterations 1–2 reds correctly. The gate exits 0, so this is advisory — but a guard whose falsifier
cannot red it is a green light that means nothing, and each already has a diagnosis:

| guard | why the falsifier misses |
|---|---|
| `test_THE_CREATE_PATH_IS_NOT_THE_LEGACY_TOOL` | the falsifier edits `agent-runtime-vocabularies.json`; the test reads the **hardcoded `vocab()` fixture**, so the registry it claims to protect is never asserted against |
| `test_THERE_IS_NO_FUZZY_SUBSTITUTION_ARM` | the injected arm compares `_normalise('place')` against the book's kinds, and `place` does not normalise to `location` — so the value stays unknown and the guard stays green |
| `test_A_MISSING_OR_WRONG_SHAPE_YIELDS_NOTHING_RATHER_THAN_RAISING` | `seq = [seq]` is caught by the per-row `isinstance` check downstream, so the wrong shape still yields nothing instead of raising |
| `test_NO_FEDERATED_TOOL_DECLARES_ITS_OWN_OWNER` | it injects `_meta_forged`, a key nothing reads; forging the owner needs the tool's real `_meta.served_by` |
| `test_THE_UNION_DERIVES_COMPLETELY` | the replacement still appends whenever a name exists, so it is a no-op on every catalogue row |

### D-2 · Running the falsification harness concurrently with the suite reds tree-mirroring guards

`test_NEITHER_CENSUS_WRITER_CAN_REACH_THE_LIVE_TREE__all_8_cells` went red mid-iteration, and
**reproduced at two earlier commits in a detached worktree** — which looked like a long-standing
break until the variable turned out to be a background `--run` competing for temp mirrors. It
passes clean (23.75s) once nothing else is running. Run the gates serially; a red here is a
scheduling artefact before it is a defect.

**And it cost me a wrong edit before I understood it.** The same racing run reported
`surface.py::SurfaceAssembler.assemble::AssertionError::1` as `NOW GUARDED`, so I dropped it from
the census allowlist — checking only the failure mode the allowlist's header names (digest churn),
which this was not. A clean re-run (159 sites, 12 workers, nothing competing) reports it
`NEWLY SILENT` again, and the row is restored. **A verdict from a gate that was racing another
mirroring gate is not evidence, and it fails in the flattering direction — it claims a guard
exists.** The two vocabulary rows in the same report were real: they are guarded now and gone
from the clean run, which is how the corrupted and the genuine findings are told apart after
the fact.

---

## Ledger

`contracts/agent-runtime-toolv2-ledger.json` records the **conclusion** per tool and nothing else —
it never defines the set, so it cannot flatter the progress number. `--status` computes coverage
against the catalogue every time.
