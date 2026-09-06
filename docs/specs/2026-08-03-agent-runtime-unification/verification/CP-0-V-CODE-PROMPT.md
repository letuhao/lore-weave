# CP-0 · V-CODE — verifier prompt

*Committed when CP-0 opened, before the code existed. Hand the contents below to a fresh agent verbatim.*

---

You are verifying a checkpoint in the LoreWeave repository (`d:\Works\source\lore-weave`). You did not
write this code and you must not assume the person who did was careful. **Read source. Do not run the
system** — a live run is another verifier's job, and a docstring is never behaviour.

## The claim you are testing

> CP-0 installs an **instrument**: after it, the database records what the model was actually offered,
> what was withheld from it and why, whether a result came from a tool or from our own code, and how
> every turn ended — on **every** path, with **no path that skips them**.

Seven items are claimed. Verify each **independently**; a checkpoint is not an average.

| # | claim |
|---|---|
| 0.1 | `chat_messages.advertised_tools` exists and is **`jsonb` holding one entry per model pass**, each `{pass, tool_choice, names[]}` |
| 0.2 | `chat_messages.withheld_tools` exists as `[{tool, stage, reason}]`, and the budget function that drops tools **returns what it dropped** rather than discarding it |
| 0.3 | every entry in `chat_messages.tool_calls` carries **`source ∈ {tool, breaker, meta}`** and `latency_ms` |
| 0.4 | **every terminal path** writes an outcome — including cancellation and crash, not only clean completion |
| 0.5 | the frozen baseline lives in `contracts/` and the A–E arm scripts are committed |
| 0.6 | the binding-format measurement is scripted and its output committed |
| 0.7 | **`runtime_variant`** and the **declaration identity** are recorded on every recorded call |

## Where to look

- `services/chat-service/app/db/migrate.py` — schema. **This is a ledger.** A repository rule learned
  the hard way: *DDL appended to an already-applied ledger step is a silent no-op.* A new column
  therefore requires a **new chain entry**, and a test proving that entry **is in the chain**. Check
  this specifically; it is the most likely way item 0.1/0.2/0.7 is written but never actually applied.
- `services/chat-service/app/models.py` — does the row model carry the new fields, or does the column
  exist while nothing reads or writes it?
- `services/chat-service/app/services/stream_service.py` — the write sites. This file is ~5,000 lines
  and has **many** terminal paths.
- `services/chat-service/app/services/tool_surface.py` — the budget/drop logic for 0.2.
- `services/chat-service/tests/` — the tests. Judge them (see below); do not trust them.

## Your primary mandate: find the bypass

For **each** of the seven items, answer: **what is the code path that reaches the end of a turn
without writing this field?** Name it with `file:line` or state that you searched and found none, and
say how you searched.

Specific hunting grounds, all of them real defects found in this repository before:

1. **The exempting docstring.** A validator here (`require_meta`) ships its own documented exemption.
   Does any new gate describe a condition under which it declines to apply?
2. **The unapplied migration.** See the ledger note above.
3. **The write-only column.** A field added to schema and to the write path, but whose value is never
   read back, cannot be shown to be correct. `finish_reason='streaming'` rows are written in this
   codebase and **never read**. Is any new field in that state?
4. **The partial terminal path.** 0.4 says *mandatory on every terminal path*. Enumerate the terminal
   paths in `stream_service.py` — normal stop, tool-loop breaker exit, cancellation/abort, exception,
   timeout, spend-gate refusal, and any others you find. **For each one, does an outcome get written?**
   Report the enumeration, not a summary.
5. **The scalar that should be an array.** 0.1 fails if `advertised_tools` records only the final pass.
   A turn with several model passes must produce several entries. Does the write path **append**, or
   does it overwrite?
6. **`source` defaulting to `tool`.** If entries lacking an explicit source are treated as `tool`,
   then breaker-minted results are silently miscounted as tool errors — which is the exact fraction
   this field exists to separate. Is there such a default?

## Judge the tests, do not rely on them

This repository has a standing rule: **a test may reject; it may never admit.** Five recorded cases
here of a green test over an artifact no consumer receives. For each new test ask:

- **is it red-able** — would it actually fail if the behaviour were removed? Say how you determined
  this. (You may reason about it statically; you may not edit tracked files to prove it.)
- does it assert over **the artifact the consumer receives**, or over an intermediate the test itself
  constructed?
- does `assert x is not None` stand in for asserting the value is *right*? A row rendering `undefined`
  is present, visible, and blank.

## Vacuity (NV-1..6)

A gate that cannot fire is worse than no gate, because it reports safety. For every check CP-0 adds,
state whether a realistic input exists that makes it fire. If a gate's subject never occurs in
practice, that is a `FAIL` finding even if the code is correct.

## Output

Write your verdict to `docs/specs/2026-08-03-agent-runtime-unification/verification/CP-0-v-code.md`:

1. **Verdict**: `PASS` / `FAIL` / `CANNOT DETERMINE` — overall, **and per item 0.1–0.7**.
2. **The falsifier** — state plainly *what you looked for that would have made this FAIL*. A `PASS`
   with no falsifier is recorded as `CANNOT DETERMINE` and does not close the checkpoint. If you could
   not determine something, say so; that is a legitimate and useful verdict, not a failure on your part.
3. **Findings**, each with `file:line`.
4. **The bypass table** — one row per item, naming the path that skips it, or the search that found none.

Do not propose fixes. Do not grade intent. If an item is well-built, say so briefly and spend your
words on the ones that are not.
