# /goal-prompt — emit a `/goal` condition from a plan

Print the goal prompt for a plan or RUN-STATE, ready to paste after `/goal`.

## Run

```bash
python scripts/goal-prompt.py --plan <path> --check && python scripts/goal-prompt.py --plan <path>
```

`--check` first: budget, headroom, whether every derived hand-back actually reached the
output, and whether an open row is unreachable. Then print the prompt.

`--plan` is required unless exactly one `docs/plans/*RUN-STATE.md` exists — with several,
guessing by mtime and printing a 4000-character goal for the wrong one is the failure this
command exists to prevent, so it refuses instead.

Give the user the output in a single fenced block, on its own, with no commentary inside it —
they select and paste it whole. **The output already begins with `/goal `**, so it is one paste
and not a paste plus a typed command. Say in one line above the block what the character count
is against the 4000 budget, and repeat any `WARN` line `--check` produced.

## Why this is a command and not a paragraph you retype

`/goal` takes a **4000-character** condition, and it was being retyped every session. Both
failure modes have already happened:

- **Stale.** A goal prompt naming a finished row sends a whole session at the wrong task —
  which is how one row held the RESUME pointer for ten consecutive batches after it shipped.
- **Over budget.** The first hand-written version was 4819 characters and `/goal` refused it.
  That refusal was luck: the natural repair under time pressure is to cut from the bottom, and
  the bottom is the **STOP** list — the half that makes a long autonomous run safe.

So the invariant half lives in `scripts/goal-prompt.py` (the cycle contract, the stop shape,
the budget) and the variable half — which rows are open, what comes next — is read off the plan
on every invocation. **A row that gets ticked leaves the queue by itself.**

## It is plan-agnostic, and that was deliberate work

The tool this was copied from was welded to one plan in one repo: the plan path, a literal
lane→row queue, the excluded row, the rules, the gates, the decision ids, and a row syntax only
one family of plans uses. All of it is now derived or declared, and the script runs with **zero
configuration** against a plan it has never seen. Proven both ways — this repo's board-table
dialect and the original's checkbox dialect, same binary, no flags.

It reads two row formats and does not need telling which:

```
- [~] **T35** — an open row            <- checkbox dialect
| `P7` the caller | `[x]` | evidence | <- board-table dialect
```

`~~`struck`~~`, `✅`, and `[x]` all mean done. `🅿`/`PARKED` means not queued — a parked row is
neither open nor finished, and treating it as open puts work the PO stopped at the head of the
queue.

## Letting a plan speak for itself

Everything below is optional; the defaults are generic and safe. A plan declares its own
specifics in one fenced block, so the rules for a run live beside the run:

````markdown
```goal-prompt
goal: the architecture is implemented correctly and a live run proves it
po_decisions: [OD-1, OD-2]
excluded: [T17]
lanes: |
  A identity §6.1 = T35, T32, T33
  B caches §6.6  = T39, T40
rules: |
  1 Measure DATA on the real stack; run CODE on the isolated one.
  2 ...
discipline: |
  ...
note: |
  T17 is NOT the head of the queue, ever again.
stop: |
  a write would touch a non-throwaway database
```
````

A **third home** — a `goal-prompt.yaml` somewhere — was considered and rejected. The rules for a
run belong beside the run or they drift from it, and a file an agent has to *find* is a file an
agent will not find.

**Lanes are optional.** Without them the queue is the plan's own board order, which is an
ordering the author already chose; a second hand-kept list is a second thing to go stale. With
lanes, an open row that no lane names is a hard error — an unreachable task is invisible in
exactly the way a finished one is.

**Do not edit the emitted text.** If it needs different content, the change belongs in the
plan's `goal-prompt` block, its board, or its RESUME line — hand-editing the output is how the
drift above starts.

## When it refuses

| exit | why |
|---|---|
| 2 | no `--plan` and no single obvious RUN-STATE · the file does not exist · it has no rows this tool can read |
| 1 | over budget, naming the RESUME and queue sizes · an open row in no declared lane · a hand-back derived but missing from the output |

Over budget is a hard error, never a truncation: a prompt silently cut to fit is one whose last
section is missing, and the last section is STOP. Fix it by shortening the plan's RESUME line —
a RESUME that will not fit in a goal prompt is too long to be read anyway — or by ticking what
is done.

## Prove it still bites

```bash
python scripts/goal-prompt.py --selftest
```

28 checks, each one a defect that was real: a ticked row leaving the queue, a parked row not
heading it, `⏸` being overloaded between *POST-REVIEW checkpoint* and *deferred with a
mechanism*, a derived marker reaching the emitted text rather than merely being computed, and
the budget check being able to go red at all.
