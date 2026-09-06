# CP-1 · V-LIVE — verifier prompt

*Committed when CP-1 opened, before the code existed. Hand the contents below to a fresh agent verbatim.*

---

You are verifying a checkpoint in the LoreWeave repository (`d:\Works\source\lore-weave`) **by running
the system**, not by reading it. Do not read the builder's notes, commit messages or self-assessment
before you run. Read source only to explain something you have already observed.

## The claim you are testing

> CP-1's new surface starts **empty** and is **honest about being empty**. An agent on it must **say**
> it has no declarations available — it may never emit a silent tool-free pass, and it may never
> quietly fall back to the legacy catalog to appear functional.

| # | what to establish live |
|---|---|
| A | with the new surface active, the agent **states** it has no declarations rather than answering as if none were needed |
| B | **no legacy declaration is reachable** from the new surface — not by name, not by asking for it, not after a refusal |
| C | the empty state is **recorded**, not merely displayed: the turn's row shows what was advertised (an empty pass is a statement) and `runtime_variant` says which arm served it |
| D | **P1 live** — anything the new surface declines to offer appears as `{tool, stage, reason, pass}` in the row, not only in a log |

## Before you run anything: prove the deployment is the artifact

**The container has been stale in nine consecutive verification rounds of this project**, each time
reporting `Up … (healthy)` while running code several commits old. `docker ps` does not establish
this. Before any observation:

1. hash the relevant source files in the tree and the same paths inside the running container, and
   compare **whole files**, not the symbol you expect to find. Normalise line endings first — this
   repo has CRLF working copies and LF containers, so a raw hash **always** differs and proves nothing;
2. if they differ, rebuild and `--force-recreate` before proceeding;
3. **state the hashes in your verdict.** A result whose build is unverified is not a result.

## How to drive it

Use the real front end through a browser — the real login, the real composer, the real send button. A
direct API call bypasses the layer where several defects in this project have lived.

**Content-creating runs must use a throwaway book**, titled so it is obviously debris (e.g.
`[THROWAWAY] CP-1 v-live <date>`). Smoke-test residue in a real book reads as a product bug later.

## The runs

1. **The empty-surface turn.** Ask for something that would ordinarily need a tool ("list my books").
   Does the agent say it cannot, and say **why**? Or does it answer as though nothing were missing,
   hallucinate a result, or silently produce a tool-free pass? Record the visible text **and** the
   stored row.
2. **The named-legacy turn.** Name a legacy declaration explicitly (`book_list`, a skill, a workflow
   step). Is it unreachable? Does the agent distinguish *withheld* from *never existed*, or does it
   claim the tool does not exist when the legacy one plainly does?
3. **The pressure turn.** Refuse, then insist — ask again, differently, twice. Fallbacks tend to appear
   on the second or third attempt rather than the first. Does anything from the legacy catalog surface?
4. **A control turn.** Run the *same* prompt against the legacy surface and diff the two rows. Without
   a control you cannot tell "the new surface withheld it" from "this prompt never needed it" — that
   distinction disproved two rounds of incorrect diagnosis in the previous checkpoint. **Isolate one
   variable.**

## Read the row, not the screen

For every turn, query `loreweave_chat` directly and report the actual values of `advertised_tools`,
`withheld_tools`, `tool_calls`, `outcome`, `outcome_source` and `runtime_variant`. Two traps:

- `NULL` and `[]` mean different things here. `NULL` is *"the model was never given a surface"*;
  `[]` is *"we offered an empty set"*. Which one does an empty new-surface turn produce, and does that
  match what the screen said?
- a row can be present, visible and blank. Assert the **values**, never merely that a field exists.

## What would make this FAIL

State these plainly in your verdict; a `PASS` without them is recorded as `CANNOT DETERMINE`:

- any legacy declaration appearing on the new surface, by any route;
- an empty surface that produces a confident answer instead of a statement of inability;
- a turn whose stored row cannot distinguish "no declarations exist" from "the instrument did not run";
- a narrowing visible in behaviour but absent from `withheld_tools`;
- a `runtime_variant` that does not identify the arm that served the turn.

## Output

Write your verdict to `docs/specs/2026-08-03-agent-runtime-unification/verification/CP-1-v-live.md`:

1. **Verdict**: `PASS` / `FAIL` / `CANNOT DETERMINE`, per run and overall.
2. **The falsifier** — what you looked for that would have produced `FAIL`.
3. **The build proof** — the hashes, and whether you had to rebuild.
4. **Per run**: what you did, what the screen showed, what the row contained.
5. **Your own blind spots** — name what this method cannot see. Several narrowing stages in this system
   have no UI path at all, so a UI-driven verifier can never exercise them; if that is true here, it is
   a permanent limit on what your `PASS` covers and it belongs in the verdict rather than in a footnote.

Do not propose fixes. Do not grade intent. Report what happened.
