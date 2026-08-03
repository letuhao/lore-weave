# CP-0 · V-LIVE — verifier prompt

*Committed when CP-0 opened, before the code existed. Hand the contents below to a fresh agent verbatim.*

---

You are verifying a checkpoint in the LoreWeave repository (`d:\Works\source\lore-weave`). Your subject
is **the running system**, not the source. Another verifier reads the code; you must not substitute for
them, and you must **not read the builder's notes or commit messages before you run**.

## The claim you are testing

> After CP-0, a real turn through the real product leaves behind a record from which an outsider can
> reconstruct **what the model was offered, what was withheld and why, which results came from tools
> rather than from our own code, and how the turn ended** — for turns that succeed, turns that fail,
> and turns nobody ever finishes.

## What you must do

Drive the **real system**, the way a user does. The services run under Docker Compose; the front end is
in `frontend/`. Prefer the actual UI path. If you drive the API directly instead, **say so in your
verdict** — it is a weaker result, because this project has a recorded case of a feature that worked in
every backend test and was wired into an editor the product no longer shipped.

**Use a throwaway book.** This repository has a standing rule that a content-creating smoke test must
never write into the dogfood book: smoke debris there reads as a product bug months later. Create your
own book, work in it, and name it in your verdict.

### The four runs, and the last two are the ones that matter

| run | what you do | what must be recorded |
|---|---|---|
| **A · clean** | any turn where the model calls at least one tool and finishes normally | `advertised_tools` present, per pass; every `tool_calls` entry has `source` and `latency_ms`; an outcome |
| **B · withheld** | a turn where the tool budget drops something (a large surface, or however the system reaches that state) | `withheld_tools` names the tool, the stage, and a reason — **not an empty array** |
| **C · cancelled** | **stop the turn mid-stream** from the UI | a terminal outcome that distinguishes *the user abandoned this* from *this broke*. `interrupted` alone is a defect, not an outcome |
| **D · killed** | kill the chat-service container mid-turn (`docker kill`), then bring it back | the turn does not sit forever in a non-terminal state with nothing recorded |

For each run, **query the database yourself** and paste the actual rows. Do not describe them.
Connection details are in the repo's compose files; the chat database is `loreweave_chat`.

### The question that decides your verdict

**Take run A's stored record and, from it alone, answer:** which tools was the model holding on its
second pass? Was anything hidden from it? Did the third result come from a tool or from our own
breaker? How did the turn end?

If you can answer all four from the record without reading code, the instrument works. **If you find
yourself inferring, it does not** — and the inference is the finding.

## Look for the failure this instrument exists to catch

There is a recorded defect in this system where a tool the model needed was **silently deleted from the
offered set mid-turn**, and nothing in production recorded it. Construct a turn where the offered set
**changes between passes** and confirm the record shows both states. If the record shows only the final
pass, that is a `FAIL` on the specific thing CP-0 was built for.

## Also report what you were not asked about

You are the only verifier touching the running system. If you see something broken — errors in logs,
a UI path that does not work, a response that contradicts what the record says happened — report it
even if it is outside CP-0. Say clearly that it is out of scope.

## Output

Write your verdict to `docs/specs/2026-08-03-agent-runtime-unification/verification/CP-0-v-live.md`:

1. **Verdict**: `PASS` / `FAIL` / `CANNOT DETERMINE`, and separately **per run A–D**.
2. **The falsifier** — *what you looked for that would have made this FAIL*. A `PASS` with no falsifier
   is recorded as `CANNOT DETERMINE`, which does not close the checkpoint.
3. **The raw rows** you pulled, and the exact queries. Paste them.
4. **How you drove the system** — UI or API, and the name of the throwaway book you used.
5. If a run was impossible to perform, say which and why. That is a finding about observability, and
   observability is this checkpoint's whole subject.

Do not propose fixes. Do not read the builder's reasoning to resolve an ambiguity — report the
ambiguity instead.
