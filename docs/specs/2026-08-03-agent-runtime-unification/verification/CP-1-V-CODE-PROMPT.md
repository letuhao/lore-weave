# CP-1 · V-CODE — verifier prompt

*Committed when CP-1 opened, before the code existed. Hand the contents below to a fresh agent verbatim.*

---

You are verifying a checkpoint in the LoreWeave repository (`d:\Works\source\lore-weave`). You did not
write this code and you must not assume the person who did was careful. **Read source. Do not run the
system** — a live run is another verifier's job, and a docstring is never behaviour.

## The claim you are testing

> CP-1 builds a **membrane**: a new declaration registry that starts **empty**, and a new assembler
> that can reach **nothing** but that registry. Old declarations are not hidden — they are **absent**.
> There is no code path from the legacy catalog to the new surface: not one behind a flag, not one
> that is disabled. Admission is **construction**: an object that exists is, by that fact, valid.

Seven items are claimed. Verify each **independently**; a checkpoint is not an average.

| # | claim |
|---|---|
| 1.1 | `contracts/agent-runtime-manifest.json` is **generated** (not hand-authored) and **starts empty** (M1) |
| 1.2 | an **import-graph gate**: the new assembler's transitive imports contain no legacy catalog, skill-registry or workflow-seed module (M2) |
| 1.3 | discovery reads the manifest **only** — a legacy-only declaration of **each of the three kinds** (tool, skill, workflow) returns **zero rows** (M3) |
| 1.4 | **construction IS validation** — `Admitted[D]` carries a private field, so producing one without passing the contract check is impossible (M4). **P4 lands here: no instrument column bound to a constant at any INSERT** |
| 1.5 | a reference to a **non-admitted** declaration is **unresolvable** — generation fails (M5) |
| 1.6 | **C-0 identity**: id · owning service **derived, never authored** · lifecycle state · contract version |
| 1.7 | **P1 — every narrowing registers `{tool, stage, reason, pass}`** on the new surface |

## Where to look

- `services/chat-service/app/agentruntime/` — the new package. Everything CP-1 adds should be here.
- `contracts/agent-runtime-manifest.json` — the manifest, and whatever generates it.
- the import gate — a working precedent exists at `scripts/lint-no-direct-llm-imports.sh`. **Is the new
  gate of that kind, or is it a lint rule / a naming convention / a comment?**
- `services/chat-service/app/services/tool_surface.py`, `tool_discovery.py`, `stream_service.py` — the
  LEGACY surface. Your interest in these is one question: **does anything in the new package import,
  call, or read a value that originates here?**
- `services/chat-service/tests/` — judge the tests; do not trust them.

## Your primary mandate: find the path from the old catalog to the new surface

For **each** of the seven items, answer: **what is the code path that defeats it?** Name it with
`file:line`, or state that you searched and found none — and say **how** you searched. A claim of
absence with no method behind it is not a finding.

Specific hunting grounds. All of these are defect shapes this repository has already produced:

1. **The membrane implemented as a filter.** The spec forbids a code path, not merely a wrong result.
   A function that reads the legacy catalog and *returns nothing from it* still **is** the path. Look
   for: a fallback when the manifest is empty; a "migration mode"; a union of two sources; a parameter
   whose default is the legacy catalog; a test helper that injects one.
2. **`Admitted[D]` in a language with no private fields.** Python has no compile-time access control —
   `_x` is a convention, `__x` is name-mangling, and both are reachable. **The claim says a bypass is
   impossible; determine what is actually true.** Can an `Admitted` be produced by `object.__new__`, by
   `dataclasses.replace`, by `copy`, by unpickling, by `model_construct`, by mutating `__dict__`, by
   subclassing? Which of those does the code prevent, and which does it merely not do? **Report the
   real boundary, not the claimed one.** If the guarantee is weaker than "compile error", say what it
   is instead — that is a useful verdict, not a failure on your part.
3. **The empty manifest that is not empty.** Does generation seed anything — a bootstrap entry, a test
   fixture, a "core" set? Does `starts empty` mean the committed file is `[]`, or that the generator
   *would* produce `[]`? Those differ, and only one is checkable.
4. **The gate that does not run.** An import-graph gate is worth exactly what CI runs. Is it wired into
   a workflow / pre-commit / the test suite? Name where it executes. **A gate present in the tree and
   absent from CI is a `FAIL`, not a partial.**
5. **The exempting docstring.** `require_meta` in this repo ships its own documented exemption. Does
   any new gate describe a condition under which it declines to apply?
6. **Derived vs authored ownership (1.6).** C-0 says owning service is **derived**. If a declaration
   can *state* its owner, the field records a claim rather than a fact. Which is it?
7. **P1's registration (1.7).** On the legacy surface this took eight attempts, every one of them a
   correct fix placed where it could not run — after the stage it instruments, or inside a branch that
   stage does not take. **Enumerate every point in the new assembler where a declaration can be
   dropped, and for each, does a `{tool, stage, reason, pass}` record get written?** Report the
   enumeration, not a summary.
8. **P4 (1.4).** Enumerate every INSERT the new runtime reaches and every value it binds. A literal
   reachable from **more than one** terminal condition is the defect; a literal reachable from exactly
   one is not. Apply that distinction rather than flagging every constant.

## Judge the tests, do not rely on them

Standing rule in this repository: **a test may reject; it may never admit.** For each new test:

- **is it red-able** — would it fail if the behaviour were removed? Say how you determined this. You
  may reason statically; **you may not edit tracked files.**
- **is it a shape gate or a behaviour gate?** A substring or `ast.walk` assertion frequently passes
  over the very defect it names — one in this repo was green while the column it guarded stored
  duplicated rows, because the forbidden string was still present in a comment. Prefer to trust a test
  that executes the mechanism.
- does `assert x is not None` stand in for asserting the value is **right**?
- for anything touching SQL or jsonb: does the test **execute** it against a database, or assert over
  the query string? The latter proves nothing about the stored value.

## Vacuity (NV-1..6)

A gate that cannot fire is worse than no gate, because it reports safety. For every check CP-1 adds,
state whether a realistic input exists that makes it fire. **A gate whose subject never occurs is a
`FAIL` finding even when the code is correct.** Note especially: with an EMPTY manifest, several of
these gates have no subject at all — decide, and say, whether each is genuinely armed or merely
untested-because-unreachable.

## Output

Write your verdict to `docs/specs/2026-08-03-agent-runtime-unification/verification/CP-1-v-code.md`:

1. **Verdict**: `PASS` / `FAIL` / `CANNOT DETERMINE` — overall, **and per item 1.1–1.7**.
2. **The falsifier** — state plainly *what you looked for that would have made this FAIL*. A `PASS`
   with no falsifier is recorded as `CANNOT DETERMINE` and does not close the checkpoint. If you could
   not determine something, say so; that is a legitimate verdict.
3. **Findings**, each with `file:line`.
4. **The bypass table** — one row per item, naming the path that defeats it, or the search that found
   none.
5. **The `Admitted[D]` boundary** — the honest statement of what is actually prevented, and by what.

Do not propose fixes. Do not grade intent. If an item is well-built, say so briefly and spend your
words on the ones that are not.
