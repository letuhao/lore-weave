# Verification — prompts written before the build, verdicts written by agents that did not build

**Why this directory exists.** `RUNSTATE` clause 3 of the deployment protocol: *a verifier prompt
authored after the code is a prompt written to pass — the same defect as acceptance criteria written
after the result.* So the prompt for checkpoint *n* is committed **when checkpoint *n* opens**, before
any of its code exists, and its commit must precede the build commits in `git log`.

| file | is | written when |
|---|---|---|
| `CP-<n>-<ROLE>-PROMPT.md` | the instruction handed verbatim to a fresh agent | **checkpoint opens** |
| `CP-<n>-<role>.md` | that agent's verdict | checkpoint closes |

**How a prompt is used.** One fresh `Agent` per role, all roles dispatched **in a single message** so
they run concurrently and cannot influence one another. The agent receives the prompt file's contents
and nothing else — **not the builder's commit messages, not its notes, not its self-assessment.**

**What a verdict must contain**, or it does not count:

- `PASS` / `FAIL` / `CANNOT DETERMINE`
- **the falsifier** — what the verifier looked for that would have produced `FAIL`. A `PASS` with no
  stated falsifier is recorded as `CANNOT DETERMINE`, and **`CANNOT DETERMINE` does not close a
  checkpoint.**
- for every claim: the file:line or the query output it rests on.

**Scale sets the roster** — α: `V-CODE` · β: `+V-LIVE` · γ: `+V-METRIC`. CP-0, CP-3 and CP-4 are γ.

**Two rules that bind the builder, not the verifier.** The builder may not answer a finding by
explaining intent — only by changing the artifact or withdrawing the claim. And the builder may not run
the verification itself and present the output as verification: running the query is evidence-gathering,
never a verdict.

**Disagreement is not settled by majority.** V-METRIC ruling a number unsound voids any V-LIVE `PASS`
that rests on it, because a result measured wrongly is not a result.
