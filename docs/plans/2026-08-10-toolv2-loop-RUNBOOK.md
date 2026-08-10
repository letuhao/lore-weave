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

---

## Ledger

`contracts/agent-runtime-toolv2-ledger.json` records the **conclusion** per tool and nothing else —
it never defines the set, so it cannot flatter the progress number. `--status` computes coverage
against the catalogue every time.
