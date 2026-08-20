# CP-1 · round 26 · V-CODE — the prompt, committed BEFORE the verifiers run

**Scope: the R26 delta only** — the twelve R25 findings and the transfer correction. Items with an
independent PASS from rounds 1–25 are not re-graded.

## 🔴 Isolation, and the hole I left in it last round

R25's isolation rule covered the repository and **not the shared scratchpad the two worktrees lived
in**. One verifier wrote a probe into a path the other could have used. Nothing was measurably
affected — but the hazard was open in the round whose headline control *is* isolation, and it was
open because I drew the boundary around the thing the previous round happened to name. **That is
finding A2's shape, committed by the prompt instead of by the code.**

So: your worktree is yours, **and so is your scratch directory**. Do not read or write anything under
`d:\Works\source\lore-weave`, under the other verifier's worktree, or under any shared temp path.
Put every temporary file inside your own worktree or your own named scratch directory. If you observe
a file changing under you, that is a finding about the method and it outranks whatever you were
measuring.

## 🔴 Two method rules, both learned the hard way in R25

* **A restore must write BYTES.** One verifier's restore used `Path.write_text` and rewrote 3,678 LF
  endings as CRLF — byte-different, meaning-identical, `git status` dirty. Third instance of that
  defect in this effort, reproduced in the round meant to catch it.
* **A restore assertion must compare BYTES.** That verifier's `read_text() == src` check **passed**
  through the corruption, because `read_text` universal-newlines it back.
* And do not assume a line ending: **check per file**. My R25 prompt said "the tree is CRLF"; both
  verifiers measured the files they touched as LF in a fresh worktree. Neither blanket is safe.

## ▶ What this delta claims

Twelve findings, each with a guard proven RED-able by reverting exactly that fix in a throwaway
mirror. ⚠️ **Builder's evidence throughout.**

| # | R25 finding | what changed |
|---|---|---|
| **A1** | CI check green under 19 of 22 shapes | the command family is now a **whitelist** — the step's live `run:` must be exactly `python scripts/agentruntime-census.py` — plus `defaults`, `shell`, `runs-on`, `needs`, `strategy` and every trigger VALUE. **36 shapes** as controls |
| **A2** | write guard caught 5 of 19 APIs | **the axis changed.** It binds the **PATH**, not the API: a taint walk from `ROOT`/`PKG`/`CS`/`ALLOWLIST` to a fixed point, refusing any tainted value reaching a non-read call. **22 vehicles** as controls, including the two you predicted a cell-list repair would miss. It also found a live defect on its first run: `_suite_is_green`'s `cwd` defaulted to the real `services/chat-service` |
| **A3** | T11d red on correct code, cross-module | alias maps are **per module plus imports**; both false-positive vehicles are now controls that must stay GREEN |
| **A4** | T11d blind to the table hoist | the SQL is flattened in **source order** and any name bound to a string literal is substituted, not only the column's |
| **A5** | W4 at the `try` door only | `s.body[:1]` at the `with`/`async with` door too, with both of your probes and a first-statement control |
| **A6** | probe gate 2 of 8, dead-token bypass | the literal is refused **anywhere**; the path must **derive** from `_swept_root()` by assignment. **10 vehicles** as controls |
| **A7** | `_mirror()` leaks on its own failure | frees what it allocated, `BaseException` |
| **B1** | import gate defeated by one prose word | the string term is narrowed to **`__all__`'s elements**, per your prescription; plus `Load` context, `rglob`, per-import, and the `attr` term removed |
| **B2** | 9/9 workflow ids fail the alphabet | `-` admitted, with the migration argument stated; and a gate that runs `_ID` over **the three live registries** |
| **B3** | `ID_MAX_LEN` guarded only from below | the vehicles are **literals** and the constant is asserted against the measurement |
| **B4** | two unfixed twins | `check_contract` exact-types both pins; the id bound now applies to `AllowList`/`DenyList`/`Filter`-on-`id`. The field-name doors are deliberately NOT bounded — reason stated |
| **B5** | 2 unreachable `except` clauses | deleted, with a guard on `check_row`'s raise **closure** rather than on the deletion |
| **F3** | an f-string is not prose-blind | `JoinedStr` is blanked wholesale |
| **F7** | transfer used a substituted criterion | **moved back to CP-1 and fixed**: `contract.check_document` is one definition for every door, 24/24 cells |

## ▶ Verifier A — the instruments

1. **A2's new axis.** The claim is that the PATH is a closed set where the API is not. **Attack the
   axis, not the vehicle list**: a path built at runtime from a string, an `os.environ` lookup, a
   name that reaches the tree without passing through `ROOT`/`PKG`/`CS`, `READS` and `PURE` being
   allow-lists that a new entry can widen silently. Is `EXEMPT = {_mirror, main}` honest?
2. **A1's whitelist.** Enumerate your own shapes again. A whitelist has its own failure mode — is
   there a way to satisfy the exact string and still not gate?
3. **A5, A6, A4/A3** — for each, is the twin fixed, and is the guard binding the property?
4. **The census's own numbers.** The digest changed for every f-string refusal, so the allowlist was
   regenerated wholesale. **That is the highest-risk change in this delta**: verify the new rows are
   the same SITES, and that the blanking has not collapsed two distinct refusals into one id.
5. **Convergence**, plus executed-vs-argued with your own denominator.

## ▶ Verifier B — the membrane

1. **F7's `check_document`.** One definition for six doors — verify it, and look for the level ABOVE
   it that nobody has consolidated yet.
2. **B2's alphabet.** `-` is now admitted. What else does that let in, and is the registry gate's
   corpus the right one? Your P2 probe should now print `0 of 9` — run it.
3. **B4b's comparand bound.** I bounded the id-comparand doors and deliberately left the field-name
   doors. Grade that decision, not just the code.
4. **B5.** The `except` clauses are gone and a closure guard replaced them. Can you make `check_row`
   raise a second class without that guard noticing?
5. **B1.** Your P1 probe should now print `NARROWED` — run it. Then enumerate your 11 dead-import
   shapes again against the narrowed gate.
6. **B3's literal.** Is `ID_MAX_LEN == 64` the right assertion, or have I replaced a self-derived
   bound with a brittle one?
7. **Convergence**, plus one new falsifiable prediction.

## ▶ Both — the two claims I most want attacked

* **That the twelve are actually closed.** My record is that every claim settled by a **control**
  has held and every claim settled by an **enumeration I chose** has been short. Six of these fixes
  ship a new enumeration.
* **The corrected transfer.** Two rows now carry different reasons and one came back to CP-1. Is the
  corrected version right, or is it a second tidy sentence over three different situations?

## ▶ Standing rules

* **A `PASS` with no stated falsifier is `CANNOT DETERMINE`.**
* **EXECUTE over an ENUMERATED space.** *Execution over a hand-picked sample is argument wearing a
  lab coat.*
* **A test satisfied by a comment is not a test** — four instances now, the latest inside the repair
  for the finding it closed.
* **Derive your own denominator.** Every ratio the builder has published in this run has been a
  lower bound, for five consecutive rounds, including from instruments built to stop that.
* Builder's record over eighteen rounds: **twelve pairs fixed at one end**; three refuted negative
  claims; four instruments that measured something adjacent to what they claimed; one broken FREEZE;
  one `atexit` that deleted the system temp directory; and one published inference whose control and
  seed agreed by construction.

## What both verdicts must contain

The falsifier per claim · a **bypass table** · a **red-ability table with your own denominator** · a
**sibling table** · a **guard table** · a **reachability verdict on every finding** · the
**executed-vs-argued ratio** · `git rev-parse HEAD` at start and finish · **and the path of the
worktree and the scratch directory you ran in.**

Write to `verification/CP-1-round26-v-code-{a,b}.md`.
