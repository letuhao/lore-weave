# QC-5 — the role check catches the misattributed betrayal, live — 2026-08-11

> **Result: the acceptance criterion is MET.** On the real acceptance book, with a real model,
> a draft that gives the betrayal to the wrong character is FLAGGED, and the same scene with
> the betrayal correctly attributed is CLEAN. The control is the point: a check that flags
> everything would also "pass" this test.

## What QC-5 asks

> *"**Assert the failure now surfaces:** the trap must be attributed to the cast-designated
> antagonist, **or** the canon check must FAIL — `canon_consistency` scoring 5/5 on a
> misattributed betrayal is the defect."*

The criterion is inverted: a green run on a misattributed draft is the failure signal.

## The run

Book `019f9f2d-…` / project `019f9f41-…`, position `at_order = 5_000_000` (chapter 5).
Snapshot fetched from the guard's own endpoint (`POST /internal/projects/{id}/fact-for-check`),
not a fixture. Judge: the account's own BYOK model, `source_language="vi"`.

Canon at ch.5 holds `Lâm Trạch -[betrayed]-> Lâm Uyên [5000000, None)`. <!-- doc-language-gate: ok -- stored entity names from the cited corpus; the assertion is only checkable against the real node names -->

| draft | roles judged | contradictions |
|---|---|---|
| **misattributed** — the betrayal given to a different character | 20 | **1** |
| **control** — the same scene, betrayal correctly attributed | 20 | **0** |

The finding, read off the candidate itself:

<!-- doc-language-gate: ok -- the judge's verdict is quoted verbatim in the book's own language; paraphrasing it would remove the evidence -->
```
ROLE: Lâm Trạch -[betrayed]-> Lâm Uyên
WHY : Đoạn văn nói Lâm Diệp phản bội Lâm Uyên, trong khi mối quan hệ thiết lập
      là Lâm Trạch phản bội Lâm Uyên.
```
<!-- doc-language-gate: end -->

(*"The passage says [the wrong character] betrayed her, while the established relationship is
that [the antagonist] betrayed her."*)

It names the right relationship, the right reason, and stays silent on the correct draft.

## Three defects this live run found in code written the same session

None of these would have shown up against a synthetic fixture. That is the argument for the
run, not a footnote to it.

1. **The verdict attached to the wrong relationship.** The prompt keyed each statement by its
   subject's `entity_id`; the model returned the id of the character it was *accusing*, which
   also appeared as another role's subject. The verdict silently landed on an unrelated
   `sibling_of` role — a finding that read correct and pointed somewhere false. Fixed by
   keying statements with a per-statement token (`role_0`, `role_1`, …) that names no
   character.

2. **The prompt's own exemption defeated the case it exists to catch.** It said a passage that
   "simply does not mention the relationship is NOT a contradiction". In a misattribution the
   passage has *replaced* the role's holder, so the true holder is exactly the name that is
   absent — and the model dutifully cleared all 20 roles. Rewritten to say that the named
   subject being ABSENT while someone else performs their role is the clearest form of the
   contradiction, not a reason to excuse it. Silence assigning the role to *nobody* is still
   exempt.

3. **The finding could not say WHICH relationship.** `entity_id` is the role's subject, and a
   subject usually holds several roles at a position (one character here holds four). Added
   `predicate` + `object_name` to the candidate.

## And one before them, on the ranking

The relevance filter selected **20 of 24** roles: a protagonist-centric cast names the
protagonist in nearly every role AND nearly every passage, so the cap decides what the judge
sees. The first ranking put both-endpoints-named first — backwards, because in a
misattribution only the OBJECT appears. Replaced with three tiers (both · object-only ·
subject-only); the betrayal role ranks 11 of 20 instead of being cut.

## What is still NOT done

This proves the **assertion** QC-5 turns on. It is not the full task: QC-5 also asks for an
end-to-end authoring flow through the real frontend, capturing the plan artifact, the drafted
chapters, the critic's per-chapter scores, and the glossary delta. That capture has not been
run — see `D-QC5-FULL-FLOW-CAPTURE`.

The role check is also **off by default** (`authoring_canon_role_check_enabled`), because
roles in force are common and enabling it adds a judge call to most scenes. This run enabled
it explicitly.

## Reproducing

```
POST /internal/projects/019f9f41-.../fact-for-check   {"entity_ids":[...],"at_order":5000000}
  → roles_in_draft(draft, snapshot) → judge_role_attribution(...)
```
Run both drafts. One flag on the misattributed draft and zero on the control is the result;
either alone is not.
