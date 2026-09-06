# CP-1 · round 8 · V-CODE — the prompt, committed BEFORE the verifiers run

Two verifiers, deployed in one message on a frozen artifact. Neither wrote a line of the code it
grades. This file is committed first so the questions cannot be adjusted to the answers.

**Artifact:** the commit named in the deployment message. Verify `git rev-parse HEAD` at start and
again before writing your verdict, and say so. **Modify no tracked file** except your own verdict.

---

## The standing rules

* **A `PASS` with no stated falsifier is `CANNOT DETERMINE`.** Say in advance what would have made
  the claim false and how you searched for it.
* **Gate behaviour, not shape.** An injection proves red-ability **only for the shape injected**. If
  a test asserts on declared types, source text, or a fixture it mutated itself, say so — the builder
  has shipped all three this run and each was green over a live defect.
* **Prove red-ability by the shape that will actually occur.** Inject through an out-of-tree pytest
  plugin or a monkeypatch; **never** revert an injection with `git checkout <file>` — it discards
  real work in the same file.
* **Tests may REJECT, never ADMIT.** A test that passes when the mechanism is deleted is vacuous;
  say it plainly.
* The builder has been wrong about **P4 three times** and about **U-2's wiring twice**. Prior
  correctness is not evidence.

---

## Verifier A — items 1.8 and 1.9 (U-1, U-2), and the spec they rest on

The builder claims to have fixed 16 findings from `CP-1.8-1.9-v-code.md`. Grade the **claims**, not
the diff.

1. **U-2 · does the outage reach the model on a REAL turn?** The previous round measured
   `catalog: [] | _catalogue_outage: False` end-to-end. The arming moved to the first statement of
   `stream_response` and `resume_stream_response`. **Execute the sequence** — do not read it.
   * Is there any path through either entry point on which a narrowing happens **before** the arming?
     Consider: an exception before the arm, a nested call that arms its own sink, `_emit_chat_turn`'s
     adopt branch, and a `contextvars` copy that does not propagate.
   * The gate matches by **called name** and its `_NARROWING_CALLS` list is hand-kept. The builder
     disclosed an **alias** blind spot. **Find a second way past it** and say whether it is realistic.
2. **U-2 · all three turn shapes.** Fresh, admin, resume. For each, does the outage (a) register and
   (b) reach the model? The admin catalogue fetch was moved above prompt assembly — **did that move
   break anything** (double fetch, a turn that now fetches when it should not, `tool_defs` empty
   where it was populated)?
3. **U-1 · is the whole definition composed now?** `_nfc_text` covers `description`/`title`/`summary`
   at any depth plus all of `_meta`; identifiers are left verbatim **on purpose** and `_tool_tokens`
   composes before counting. **Attack the seam:** find a string that reaches a consumer which
   assumes NFC and is still decomposed. Consumers include the estimator, the embedder, `canon.digest`
   and anything that compares two catalogue snapshots. Is leaving identifiers verbatim **safe**, or
   does some path compare a stored identifier against a composed one?
4. **1.8a · is the kind set closed?** Membership is `type(s) in _KIND_SET` at `validate_pipeline`,
   and `Filter.value` is bounded to a scalar or a tuple of scalars. **Find a third route to arbitrary
   logic.** Consider: `__hash__`, `__bool__`, `__index__`, a `str` subclass that is exactly `str` by
   `type()` but lies elsewhere, `AllowList.names` elements, `OrderBy.keys`, a stage constructed
   before a monkeypatch, and anything that reaches `_narrow` without passing `validate_pipeline`.
5. **The tests.** For each test the builder added, state whether it is red-able **by the shape that
   will occur** and whether it can pass over the defect it names. Name any that assert on source
   text or on a fixture they mutated.
6. **§0.14 and §0.14.1c.** The builder rewrote four overstatements and added a built-vs-UNBUILT
   table. **Is the table true?** Check each row against the code. A row claiming "built and gated"
   whose gate cannot fire is the same failure this section keeps repeating.

---

## Verifier B — item 1.4's P4 half, round 8

Round 7 returned FAIL on four grounds. The builder claims all four are closed and that §6.4's second
field is restored. **The builder has now been wrong about P4 three times, in three different
directions** — a constant that could not differ, a carry that could not move, and a
"no subject at CP-1" ruling that was reasoning from where the property was expected to live.

1. **Does the queue DRAIN, and can it also FILL?** Execute a real sequence through `generate()`
   against one path across an amendment: admit, amend, re-admit some, not others. Show the queue
   going non-empty and then empty. If either direction is unreachable, that is the finding.
2. **Is `contract_version` genuinely the origin?** Can you make a row's origin change? Can you make
   two rows carry different origins **and** different admissions? Can a row end up with an origin
   NEWER than its admission — and if so, does anything reject it?
3. **`bootstrap=`.** It gates the fail-open erasure. **Find the way around it**: a caller that passes
   `bootstrap=True` reflexively, a path where `manifest_path()` returns something that exists but is
   empty, a `build()` call with `previous=None` that is not `generate()`. `build()` is exported.
4. **Red-ability, by the shape that will occur.** Round 7's finding was that deleting `previous=`
   from `generate()` left 89/89 green. **Repeat that injection and three more of your choosing.**
   Report the baseline count and each result in a table.
5. **The write-side validation.** `build()` now rejects a malformed `previous`. Does it reject
   *everything* a real corrupted manifest could carry? Does rejecting make any legitimate operation
   impossible — in particular, can a manifest written by an older version still be read?
6. **§6.4's UNBUILT clause.** The builder recorded *"without leaving the runtime"* as unbuilt and
   assigned it to CP-4. **Is that assignment honest, or is it a deferral of the half that makes the
   mechanism mean anything?** Say which, with reasons.

---

## What both verdicts must contain

* The falsifier, per claim, stated before the search.
* A **bypass table**: what the property asserts, and the path that defeats it (or "none found, and
  here is how I searched").
* A **red-ability table**: injection, what it models, result, baseline.
* A **sibling table**: for each fix, the sibling you looked for and whether it was also fixed. The
  recurring failure in this run is a correction applied to one member of a set.
* `git rev-parse HEAD` at start and finish.

Write to `verification/CP-1-round8-v-code-{a,b}.md`.
