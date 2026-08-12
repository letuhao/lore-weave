# QC-5 re-run against the complete cast — 2026-08-12

**Verdict: still does not pass. The original failure mode is GONE; a different one is in
its place.**

QC-5's earlier run (2026-08-11) was measured against a knowledge graph missing two of every
five entities — `D-GLOSSARY-KG-MIRROR-HAS-NO-RECONCILER`, 17 of 43 absent. That hole is
closed, so this re-runs the acceptance assertion against a canon the check can actually see.

Run on the **isolated stack** (`infra/iso.sh`, ports +20000). The shared stack no longer
serves this branch's code — the other branch rebuilt `infra-knowledge-service` mid-session.

## What changed in the canon the check reads

```
                            before repair   after repair
:Entity with a glossary id           26            43
fact-for-check snapshot @ 11e6       16            43
relations                            31            31    (unchanged — different projection)
```

The 17 restored entities were 4 characters, 7 events, 1 item, 1 location, 1 organization,
2 power-system terms and 1 terminology entry. **One of them is directly load-bearing for
this test:**

<!-- doc-language-gate: ok -- stored node names from the cited corpus; the identity the evidence turns on is the name itself -->
`Sự phản bội tại khởi đầu` — "the betrayal at the beginning", the event-phrase-promoted-to-
entity that `D-QC5-ACCEPTANCE-BOOK-ROLES-UNPLACED` identified as the malformed subject of
the betrayal edge — **was one of the 17 missing.** It is in the graph now.

⚠️ **But the two principals of the acceptance case were NOT missing.** `Lục Vô Tội` and
`Lâm Trạch` were both among the 26 already mirrored, so the specific misattribution this
test turns on was always visible to the check. The earlier claim that judge-precision
results were measured "about entities it could not see" is therefore **too broad**: it
holds for the cast at large and not for this case's principals.
<!-- doc-language-gate: end -->

## The experiment

Two arms of the same drafted passage, differing in exactly one substitution — who commits
the betrayal. Arm A is what the drafter generated; arm B replaces the betrayer with the
canon-designated antagonist. Six canon rules in force. Three runs per arm.

<!-- doc-language-gate: ok -- the canon rules and judge output are the cited corpus and the measurement subject; translating them would destroy the identity comparison -->

```
ARM A · MISATTRIBUTED (Lục Vô Tội betrays)     run 1..3: canon_consistency=3, violations=2
ARM B · CORRECTED     (Lâm Trạch betrays)      run 1..3: canon_consistency=3, violations=2
```

Identical score. Identical two rules cited. **Zero variance across six runs.**

### The reasoning, verbatim

Rule `…cc1cbe37bc29`:
> Lâm Trạch là người anh em họ của Lâm Uyên, và chính Lâm Trạch là kẻ phản bội Lâm Uyên.
> Không ai khác là kẻ phản bội trong cạm bẫy tại Lâm gia.

**Arm A** — flagged `violated=true`, and the stated reason is the *passage's own claim
recited as fact*:
> Lục Vô Tội là người anh em họ của Lâm Trạch và chính ông ta đã phản bội Lâm Uyên. Trong
> cạm bẫy tại Lâm gia, không ai khác là kẻ phản bội.

That is not an explanation of a contradiction. It is the judge restating what the passage
says, with the verdict flag set to `true` beside it. **The flag is right by accident.**

**Arm B** — the passage was edited so that Lâm Trạch *is* the betrayer, exactly as the rule
requires. Still flagged `violated=true`:
> The passage contradicts [R1] by showing that Lin Zhe is not the betrayer but rather a
> cold and unfeeling observer.

This is simply wrong. Two further tells in one sentence: it answers in **English** where
arm A answered in Vietnamese, and it renders `Lâm Trạch` as **"Lin Zhe"** — a Mandarin
romanisation of the same Sino-Vietnamese name, i.e. cross-language identity drift inside
the judge.
<!-- doc-language-gate: end -->

### The control — the check is NOT simply flagging everything

A passage that makes no claim about any character (weather, a courtyard, no one present),
so it *cannot* contradict a rule about who betrayed whom:

```
CONTROL run 1: canon_consistency=5  violations=0
CONTROL run 2: canon_consistency=5  violations=0
```

Clean. The check has a working floor and responds to content. What it cannot do is tell a
**correct** attribution from an **incorrect** one.

## Verdict against QC-5's stated criterion

> *"the trap must be attributed to the cast-designated antagonist, **or** the canon check
> must FAIL — `canon_consistency` scoring 5/5 on a misattributed betrayal is the defect,
> and a pass here with 5/5 means the refactor has not landed."*

Taken literally, the named defect **is not reproduced**: arm A scores **3, not 5/5**, and it
does cite the betrayal rule. The blindness the refactor targeted is gone.

But that is not sufficient to call it a pass, because the identical verdict lands on the
**correct** arm. A flag that fires the same way whether the passage is right or wrong is not
detection — it carries no information about the thing QC-5 measures. And on arm B the
check is not merely uninformative, it is **actively wrong**: it asserts the passage
contradicts a rule that the passage satisfies.

**QC-5 does not pass.** The failure has moved from *"scores 5/5 on a misattributed
betrayal"* to *"cannot distinguish a misattributed betrayal from a correct one, and
mis-reasons about the correct one"*.

## What this run did NOT produce

QC-5 names four artefacts. This produced one and a half:

| Artefact | Status |
|---|---|
| the critic's per-chapter scores | **partial** — per-ARM scores on the acceptance passage, not a per-chapter pass over all three chapters |
| the plan artifact | not produced |
| the drafted chapters | reused the existing draft; not re-generated |
| the glossary delta (entity count before/after the cast pass) | not produced |

Those three require the **end-to-end authoring flow through the real frontend**, which is a
long, spend-bearing run and is still not started (`D-QC5-FULL-FLOW-CAPTURE`). Recording
QC-5 as done on the strength of this file would be the accounting artefact this plan's
verification script exists to prevent.

## Reproduce

```bash
cd infra && ./iso.sh up -d composition-service ai-gateway provider-registry-service
# two arms, three runs each, against job 019ff423-db33-78b1-aa5f-3348e433e9c8
python <scratch>/qc5_forensic_iso.py <token> <draft> <rules>
```
