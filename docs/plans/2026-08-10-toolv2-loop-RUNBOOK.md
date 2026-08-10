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

## Ledger

`contracts/agent-runtime-toolv2-ledger.json` records the **conclusion** per tool and nothing else —
it never defines the set, so it cannot flatter the progress number. `--status` computes coverage
against the catalogue every time.
