# CP-1 · round 9 · V-CODE — the prompt, committed BEFORE the verifiers run

**Scope: THE DELTA ONLY.** Items carrying an independent PASS from rounds 1–8 are not re-graded.
Round 9 exists because four things were fixed *after* round 8's verdicts and are verified by nobody
but their author — and in this run, every gap of exactly that shape has contained a defect. Round 7's
fixes were green, complete-looking, and one of them **armed a crash that killed the turn before the
model was called**.

**Artifact:** the commit named in the deployment message. Verify `git rev-parse HEAD` at the start
and again before writing your verdict, and report both. **Modify no tracked file** except your own
verdict. **Never `git checkout` any file** — it discards real work in the same file.

---

## Standing rules

* **A `PASS` with no stated falsifier is `CANNOT DETERMINE`.** Say in advance what would have made
  the claim false, and how you searched for it.
* **Gate behaviour, not shape.** A test asserting on declared types, on source text, or on a fixture
  it mutated itself is vacuous — the builder has shipped all three this run, each green over a live
  defect.
* **Prove red-ability by the shape that will actually occur.** Inject via an out-of-tree pytest
  plugin or a monkeypatch, against a scratch copy.
* **EXECUTE, do not read.** Every "measured" claim must come from code you ran. Reading and reasoning
  is how rounds 5, 6, 7 and 8 each shipped a defect.
* **The builder has been wrong about P4 three times and about U-2's wiring twice.** Prior correctness
  is not evidence.

---

## Verifier A — U-2, the P0 crash, and CP-0's drain path

1. **The P0, first, because it is the most recent and the least reviewed.** A catalogue-outage record
   carries no `tool`; the sink drain used to index `_sw["tool"]`. The fix adds
   `AdvertisedToolsRecorder.record_catalogue_withheld` and a scope dispatch at two sites.
   * **Drive it.** Find *any* path on which a catalogue-scope row reaches a consumer that assumes a
     `tool` key. Consider: `withheld_json`'s reconciliation, the DB write, `segment_merge_sql`'s
     jsonb merge, anything reading `withheld_tools` back out, and the FE contract.
   * Does the row **survive** to the persisted column, or is it dropped somewhere between the sink
     and the database? A row that crashes nothing and arrives nowhere is the same silence U-2 exists
     to end.
   * Is `count` handled consistently — absent when unknown, never fabricated as `0`?
2. **The rebuilt arm-order gate.** It now discovers entry points from the parse tree, follows
   module-local helpers **one level**, requires the arm at top level of the body, and flags aliases.
   The builder disclosed that it matches by **called name**. **Find a fifth route past it.** Consider:
   two levels of helper, a method rather than a module function, a decorator, `functools.partial`, a
   narrowing inside a comprehension or a nested function, an entry point in a module not in
   `_TURN_MODULES`, and an entry point whose name starts with `_`.
3. **`voice_stream_response` was armed this round.** Does the arming actually cover what that turn
   narrows? Drive the sequence.
4. **U-1's admin door** was fixed after round 8's verdict: `get_admin_tool_definitions` now composes,
   and the `mcp not installed` branch registers an outage. **Verify both by execution**, and find the
   sibling neither fix reached.

## Verifier B — 1.8a's operand bounds, and P4's code changes

1. **Every stage parameter is now bounded by exact type**, membership is by identity, `TopK(k=0)` is
   refused, and both list kinds reject an empty `names`. **Find a seventh operand or an eighth route
   to arbitrary logic.** Consider: `__init_subclass__`, `__class_getitem__`, a `tuple` subclass,
   `__iter__` on something that passed `type(x) is tuple`, values reaching `canon` or `asdict`, and
   anything in `OrderBy.sort`'s comparison path.
2. **`build()` now refuses to write a manifest that loses a declaration present in `previous`.**
   * Is that refusal **reachable in the way it will actually occur**, or only from a hand-built
     `previous`?
   * Does it break any legitimate operation? In particular: bootstrap, the drift gate's `build([])`,
     and a manifest whose previous content is itself invalid.
3. **The migration backfill** — a row with `admitted_against` and no `contract_version` adopts the
   former as its origin. **Is that safe, or does it launder a bogus stamp into an origin?** Can you
   construct a document that is accepted now and would have been rejected before, in a way that
   matters?
4. **Document-level stamps and `lifecycle` are now validated on read.** Verify by execution. Does
   requiring `lifecycle` break any row the generator itself produces?
5. **The P4 defect-assertion test.** `test_THE_QUEUE_IS_EMPTY_BY_CONSTRUCTION__P4_IS_NOT_SATISFIED_HERE`
   deliberately asserts a failure. **Is it honest?** It must (a) fail if the queue ever becomes
   satisfiable, and (b) not pass for some *other* reason — e.g. because `build` raised, or because
   the amendment helper did not actually amend. Drive it.
6. **The PO transfer, as a claim rather than a decision.** RUNSTATE and §6.4.1 say `contract_version`
   *"varies between rows and is carried across regeneration"* and is **gated**. Verify that
   independently: can you make two rows carry different origins through the real writer, and does a
   test red if the carry is removed?

---

## What both verdicts must contain

* The falsifier per claim, stated before the search.
* A **bypass table**: what the property asserts, and the path that defeats it — or "none found, and
  here is how I searched".
* A **red-ability table**: injection, what it models, result, and the baseline count you measured
  yourself.
* A **sibling table**: for each fix, the sibling you looked for and whether it was also fixed. The
  recurring failure in this run is a correction applied to one member of a set.
* `git rev-parse HEAD` at start and finish.

Write to `verification/CP-1-round9-v-code-{a,b}.md`.
