# QC-5 — the critic's per-chapter scores, captured — 2026-08-12

> **Result: the artefact QC-5 names is now produced, and producing it shows the acceptance
> assertion cannot be evaluated on this book.** The acceptance book has **zero active canon
> rules**, so `canon_consistency` — the exact number QC-5's pass/fail rule is written in terms
> of — was scored against nothing. A bite with two injected rules proves the machinery does
> respond, and in the same run proves the per-rule verdicts are **not per-rule**.

## Why this run existed

`D-QC5-FULL-FLOW-CAPTURE` closed three of the four artefacts QC-5 names and recorded the
fourth as missing, precisely:

> *"the critic's per-chapter scores"* — the canon envelope carries per-CHECK statuses
> (`canon_cast` · `plan_liveness` · `name_grounding`), **not** the 4-dimension `judge_prose`
> scores. Those come from the D5 continuity critic, a different pass this endpoint does not run.

This run drives that pass: `POST /v1/composition/jobs/{job_id}/critique`, the endpoint that
calls `judge_prose`, on every completed draft of the acceptance book
(project `019f9f41-…`, book `019f9f2d-…`).

**Image freshness checked first**, because this plan already lost a run to it: the
composition-service image was built `2026-08-11T22:33Z`, and the last commit touching
`services/composition-service` is `96b5ebf2d` at `2026-08-11T11:27Z`. The image is ~11 hours
newer than the code it runs. (Run 2 of the earlier capture was lost to exactly this, with the
flag correctly set — *the flag was never the stale thing*.)

## The artefact — 4 dimensions, per chapter

| job | draft chars | coherence | voice_match | pacing | **canon_consistency** | violations |
|---|---|---|---|---|---|---|
| `019ff029-…` (ch. 11, *the trap closes*) | 4109 | 5 | 4 | 5 | **0** | 0 |
| `019ff034-…` (calibration re-run) | 8019 | 5 | 5 | 4 | **5** | 0 |
| `019ff025-…` | 4762 | 5 | 5 | 4 | **5** | 0 |
| `019ff011-…` | 8556 | 5 | 5 | 4 | **5** | 0 |

`0` is a real score, not "unjudged": `_coerce_score` returns `None` for a missing or malformed
dimension and the contract distinguishes them, so a zero is the judge scoring zero.

## 🔴 The finding: the number QC-5 is written in terms of was scored against nothing

QC-5's rule is inverted and specific:

> **Assert the failure now surfaces:** the trap must be attributed to the cast-designated
> antagonist, **or** the canon check must FAIL — `canon_consistency` scoring 5/5 on a
> misattributed betrayal is the defect, and a pass here with 5/5 means the refactor has not
> landed.

Three of four chapters score exactly **5/5**. Read literally, that is the failure signal. It is
not, and the reason is measurable rather than arguable:

```
canon_rule rows for project 019f9f41-…    0
canon_rule rows for book   019f9f2d-…     0
canon_rule rows repo-wide                52   (50 active, across 46 projects)
```

The endpoint resolves the rule set at critique time — `rules = await canon.list_active(job.project_id)`
— and for this project that returns an empty list. It then passes **`present_facts=[]`
literally**, hardcoded at the call site. Both inputs to the canon dimension are empty, so
`canon_consistency` is not measuring canon on this book; a 5/5 means "nothing to contradict"
and the 0/5 on chapter 11 is a worst-possible score **citing no violation at all**.

**So QC-5's criterion is not satisfied and not refuted — it is unevaluable on this data**, which
is the same shape as `D-QC5-ACCEPTANCE-BOOK-ROLES-UNPLACED` one layer over: the assertion is
sound, the acceptance corpus cannot carry it.

## 🧪 BITE — does `canon_consistency` respond to anything?

A score of 0 against an empty rule set could mean the dimension is inert. Two canon rules were
inserted on the acceptance project, chosen so the drafted passage settles each one plainly, then
deleted after the run:

| rule | text | what the passage does |
|---|---|---|
| `0331a53f` | *Lam Trach died before the story begins and never appears in any scene.* | **flatly contradicts it** — he is present and betraying |
| `6e153c35` | *Lam Uyen is a member of the Lam family.* | **plainly satisfies it** — stated in the opening line |

Re-running the identical job, judge, passage and critic:

```
                       coherence  voice_match  pacing  canon_consistency  violations
0 rules (baseline)         5           4          5           0               0
2 rules (bite)             4           5          3           2               2
```

<!-- doc-language-gate: ok -- the judge's verbatim verdicts on cited-corpus names. The evidence this section turns on IS the raw string: the second reason is a byte-for-byte copy of the first, which paraphrasing would destroy. -->
```
rule 0331a53f  violated = True  | Trong canon, Lam Trach đã chết và không xuất hiện trong bất kỳ cảnh nào.
rule 6e153c35  violated = True  | Trong canon, Lam Trach đã chết và không xuất hiện trong bất kỳ cảnh nào.
```
<!-- doc-language-gate: end -->

**Stable across three byte-identical runs** — `4/5/3/2` with both verdicts identical each time.
Unlike the `judge_role_attribution` experiments (0 / 4 / 12 on identical input), this is
deterministic, so the two findings below are properties of the check, not sampling noise.

### The machinery works, and the verdicts are not per-rule

**Good:** the path is live end-to-end. Rules reach the judge, `canon_consistency` moves 0 → 2,
`violations[]` populates, and the contradicted rule is flagged **with the correct reason**.

**🔴 The control was flagged too, with the other rule's reason copied verbatim.** *"Lam Uyen is
a member of the Lam family"* is confirmed by the passage's first sentence, and it comes back
`violated: true` carrying the *Lam Trach died* explanation. The verdict is keyed to a rule id
whose reason belongs to a different rule.

That is the same defect class this plan already recorded one judge over — *"the verdict attached
to the wrong relationship (subject-id keying → per-statement token)"* and *"a finding that could
not say which relationship it was about"* — now measured in `judge_prose`. **A per-rule verdict
that cannot say which rule it is about is not a per-rule verdict**, and an author acting on it
would be sent to correct a sentence that is already correct.

### And the prose dimensions moved on byte-identical prose

`coherence 5 → 4` and `pacing 5 → 3` between the two runs above. **Nothing about the prose
changed** — only two canon rules were added to the prompt. The three craft dimensions are
supposed to be independent of the canon rule list; they are not, so a book that acquires canon
rules will see its prose scores shift for reasons that have nothing to do with its prose.

## What this run does and does not establish

**Does:** the fourth artefact exists · the critique path runs end-to-end on real drafts through
the real endpoint · `canon_consistency` genuinely responds to canon rules · two distinct,
reproducible defects in `judge_prose` are now measured rather than suspected.

**Does not:** QC-5's acceptance assertion is still unproven, because the book carries no canon
rules and the endpoint supplies no present facts. **A green here would have been the accounting
artefact** the plan's verification script exists to prevent — three chapters at 5/5 look exactly
like a passing canon check and are nothing of the kind.

## Cleanup

Both injected rules deleted (`DELETE 2`); `canon_rule` rows for the acceptance project back to
**0**, repo-wide `QC5-BITE-%` rows **0**. No other write was made — the critique endpoint is
read-only with respect to glossary and knowledge, and `persist:false` was never needed because
no generation ran.
