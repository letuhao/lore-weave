# QC-5 — the drafting run, 2026-08-13

**All three chapters drafted. The canon check covered ONE of its three checks on every one of
them, so "0 violations" is not evidence of canon consistency — it is the output of a check
that mostly did not run.**

Run on the isolated stack (`infra/iso.sh`). Drafter: Gemma-4 26B-A4B QAT via
provider-registry → LM Studio.

## What ran

`POST /v1/composition/works/{work}/chapters/{chapter}/generate` — the B2 chapter single-pass:
*"generate a WHOLE chapter in ONE drafter pass from its A3 decompose plan, grounded at the
chapter reading position, then run a chapter-level canon check+reflect over the union cast."*

<!-- doc-language-gate: ok -- the UI control name is quoted so the next session can find it -->
⚠️ **Not driven through the studio UI.** QC-5 asks for the flow "through the real frontend".
The UI's plan-driven drafting sits behind the agent-run surface (`Đường ray Tiến trình`), which
I could not locate as a single control; this drives the same endpoint the UI drives, with the
same user's auth through the same service. Stated rather than glossed — it is a real gap
against the task's wording.
<!-- doc-language-gate: end -->

## Artefact 2 — the drafted chapters

<!-- doc-language-gate: ok -- chapter titles from the cited corpus; they identify which chapters ran -->
```
ch  title                              words   tokens in/out
11  Cạm bẫy khép lại                     759       2441/1131
12  Hai người hắn tin nhất bước ra       918       2545/1377
13  Sự thật, rồi tuyệt vọng              972       2517/1458
                                       -----   -------------
                                        2649       7503/3966
```
<!-- doc-language-gate: end -->

All three were `word_count 0` before the run, so this is genuine generation. Accepted into the
book (`POST /jobs/{id}/persist`) — draft revision 2 on each.

**The async path does not persist, by design.** `persist: true` on the generate call returned
`persisted: false` with no error. That is not a defect: the worker "COMPUTES + stores the
result; persistence to book-service stays a separate bearer 'accept' step, since the worker has
no user bearer". The accept step is a second call, and it is what the UI does too.

## Artefact 3 — the canon result, and why it is thin

```
ch   canon_cast   plan_liveness   name_grounding   coverage            unresolved   violations
11   no_rules     no_position     checked          [name_grounding]         5            0
12   no_rules     no_position     checked          [name_grounding]         3            0
13   no_rules     no_position     checked          [name_grounding]         4            0
```

**One of three checks evaluated, on all three chapters.**

* `canon_cast: no_rules` is **not** "the canon rules are missing" — the work has **six active
  `world`-scope rules**, served fine by the API. `NO_RULES` is `check_over`'s label for an
  EMPTY CORPUS, and `canon_cast`'s corpus is the resolved cast: `len(cast_liveness) -
  len(unresolved)`. Every cast member came back `{'source': 'none', 'status': 'unknown'}`, so
  5 − 5 = 0 and the check reports an empty corpus. *(I first read this as "the check cannot see
  the rules" and had to correct myself — the enum name invites it.)*
* `plan_liveness: no_position` — the chapter carries no reading position, so the
  position-windowed read cannot run. That is `D-QC5-ACCEPTANCE-BOOK-ROLES-UNPLACED`, still open.
* `role_check: null` — not asked for on this path.

So **zero violations across three chapters says almost nothing.** And the one check with
coverage turned out to be weaker than it reads — see below.

### The check that DID run compared the draft to the drafter's own prompt

`name_grounding.py`'s docstring calls `truth_source` *"the field that matters most"*: with
`prompt_proxy` the draft's names are compared against **the packed prompt the drafter was
given**, which is a self-consistency observation, not a check against canon. The field was
**computed and then dropped before the envelope**, so no caller could read it — the run above
reports `name_grounding: checked` with no way to tell which of the two it had done.

Surfaced it (`name_truth_source` on `ReflectResult` and both envelopes) and re-ran chapter 11:

```
name_check_method : capitalised_latin
name_truth_source : prompt_proxy        <- the draft graded against its own input
```

**So the drafting run verified NOTHING against canon.** `canon_cast` had an empty corpus,
`plan_liveness` had no position, and `name_grounding` compared the draft to the prompt that
produced it. Three checks, zero comparisons to the authored SSOT.

`capitalised_latin` on a Vietnamese chapter is CORRECT, incidentally — Vietnamese is a
Latin-script language, and the Unicode tokeniser fix from `dd77f1a90` is what makes the
diacritics work. `caseless_script` is the branch for Chinese/Japanese.

⚠️ **`critic` on the job is `null`.** The 4-dimension `judge_prose` scores QC-5 calls "the
critic's per-chapter scores" come from the **D5 continuity critic**, a separate pass this
endpoint does not run — the plan already recorded that under `D-QC5-FULL-FLOW-CAPTURE`, and
this run confirms it end-to-end rather than by reading code.

## Artefact 4 — the glossary delta

```
before   46 live / 43 named
after    46 live / 43 named      delta 0
mirror   43 mirrored, 0 missing  (unchanged)
```

**Zero, and the reason is structural:** entity extraction runs on the published/parsed path,
not on a draft write. Three accepted DRAFTS change no glossary rows. A non-zero delta needs the
cast pass or a publish, neither of which this run performed.

## Where QC-5 stands after this

| # | artefact | |
|---|---|---|
| 1 | the plan artifact | ✅ captured 2026-08-12 |
| 2 | the drafted chapters | ✅ 2649 words across the three trap chapters |
| 3 | the critic's per-chapter scores | ◐ canon envelope captured; `judge_prose` scores need the D5 critic pass |
| 4 | the glossary delta | ✅ measured: **0**, with the reason |

The **acceptance assertion** passed separately on 2026-08-12
([`2026-08-12-qc5-discrimination-valid.md`](2026-08-12-qc5-discrimination-valid.md)): a
misattributed betrayal scores 2 of 5 and is rejected naming the right reason.

**What this run adds is that the assertion and the FLOW disagree about coverage.** The
two-arm experiment fed rules directly to the critique endpoint and got a real judgement. The
drafting flow's own canon check, on the same book, evaluated one check of three. QC-5 is
written in terms of `canon_consistency`, and the flow does not produce it.
