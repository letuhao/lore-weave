# QC-5 — the canon check DOES discriminate. Valid experiment, 2026-08-12

**Result: the acceptance assertion PASSES.** When the trap is attributed to the wrong
character, the canon check fails the passage and says exactly why. This supersedes
[`2026-08-12-qc5-rerun-complete-cast.md`](2026-08-12-qc5-rerun-complete-cast.md), whose
verdict was an artefact of an invalid experiment.

## Why the previous experiment was invalid

It built its two arms by substituting one character name for another in the generated
draft — and never checked what the draft says about that character. It says this, once:

<!-- doc-language-gate: ok -- the sentence IS the evidence: what the draft says about the substituted character -->
> *Nhưng ở góc khuất của đại sảnh, Lục Vô Tội chỉ đứng đó, im lặng như một pho tượng đá.*
> ("But in a hidden corner of the hall, Lục Vô Tội just stood there, silent as a stone statue.")
<!-- doc-language-gate: end -->

He never betrays anyone. **The draft names no betrayer at all** — it refers to "the
betrayers" in the plural and to being "betrayed by blood kin", and the taunting antagonist
is an unnamed *he*. So the substitution renamed a **bystander**. Both arms carried the same
content, identical verdicts were correct, and I reported that as a defect.

**Lesson, and it is not a new one here:** an A/B whose arms do not differ in the thing being
measured will produce a stable, confident, meaningless result. Read the fixture before
trusting the contrast. (Sibling: the earlier bite fixture whose rule texts looked like
identifiers and contaminated the judge's output.)

## The valid experiment

One sentence inserted into the untouched draft, at the same anchor, **identical in both arms
except the name** — so the named betrayer is the only variable:

<!-- doc-language-gate: ok -- the inserted sentence and the two names are the experiment's single variable -->
> *Chính {NAME} là kẻ đã bày ra cạm bẫy này tại Lâm gia, và {NAME} thừa nhận điều đó không
> chút hối tiếc.*
> ("It was {NAME} who laid this trap at the Lâm household, and {NAME} admitted it without
> the slightest regret.")

| arm | `{NAME}` | who that is |
|---|---|---|
| **CANON** | `Lâm Trạch` | the cast-designated antagonist — canon rule R1 names him as the betrayer |
| **WRONG** | `Lục Vô Tội` | not the antagonist — R1 ends "no one else is the betrayer" |
<!-- doc-language-gate: end -->

Six canon rules in force, three runs per arm, against the complete 43-entity cast.

## Result

```
ARM WRONG  (non-antagonist named)   score=2   violations=2   betrayal rule flagged: YES  x3
ARM CANON  (antagonist named)       score=3   violations=2   betrayal rule flagged: YES  x3
CONTROL    (cannot violate)         score=5   violations=0                               x2
```

**The scores separate — 2 vs 3 — stably, three runs each.** More important than the numbers,
the *reasons* separate, and each is correct for its arm:

<!-- doc-language-gate: ok -- the judge's verbatim reasoning is the measurement -->
**ARM WRONG** — caught for precisely the thing QC-5 exists to catch:
> *Theo [R1], Lâm Trạch là người phản bội Lâm Uyên, chứ không phải Lục Vô Tội.*
> ("According to [R1], Lâm Trạch is the one who betrayed Lâm Uyên, not Lục Vô Tội.")

**ARM CANON** — still flagged, but on a **different and defensible** ground:
> *Theo [R1], Lâm Trạch chính là kẻ phản bội Lâm Uyên và không ai khác. Passage này cho thấy
> có nhiều người khác đã tham gia vào việc phản bội…*
> ("According to [R1], Lâm Trạch is the betrayer of Lâm Uyên and no one else. This passage
> shows that several others also took part in the betrayal…")
<!-- doc-language-gate: end -->

That second objection is **correct about the untouched draft**: R1 ends *"no one else is the
betrayer"*, and the generated prose says "the betrayers", plural, and "betrayed by blood
kin". Naming the right antagonist does not remove that conflict. So the canon arm is not a
false positive — it is a second, real inconsistency the draft carries independently of the
variable under test.

## Against QC-5's stated criterion

> *"the trap must be attributed to the cast-designated antagonist, **or** the canon check
> must FAIL — `canon_consistency` scoring 5/5 on a misattributed betrayal is the defect, and
> a pass here with 5/5 means the refactor has not landed."*

A misattributed betrayal scores **2 of 5** and is rejected with the correct reason named.
Nothing scores 5/5. **The assertion half of QC-5 passes**, and the criterion's inverted trap
(a green that means failure) is not triggered.

The rule-id → verdict binding also holds at **six** rules — each `why` cites `[R1]`/`[R3]`
and resolves to the rule it is actually about — which is the fix `D-QC5-PROSE-JUDGE-VERDICT-
NOT-PER-RULE` reopened. It was previously only validated on a 2-rule fixture.

## What is still NOT done

QC-5 names four artefacts. This closes the assertion. The plan artifact, freshly drafted
chapters and the glossary delta need the end-to-end authoring flow through the real
frontend (`D-QC5-FULL-FLOW-CAPTURE`).

## Reproduce

```bash
cd infra && ./iso.sh up -d composition-service ai-gateway provider-registry-service
# arms differ only in the inserted sentence's NAME
python <scratch>/qc5_discriminate.py
```
