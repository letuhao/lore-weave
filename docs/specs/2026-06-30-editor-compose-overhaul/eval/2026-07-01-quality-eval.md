# Compose-quality evaluation — real 12-chapter book (2026-07-01)

**Method.** Drove the three quality surfaces over the REAL "Ma Nữ Nghịch Thiên (POC)" book
(12 drafted chapters, vi) through the gateway with the `tests/e2e` harness + `eval_compose_quality.py`,
model = local `gemma-26b`. Per chapter: `self-heal/propose` + `quality-report`; once at book level:
`promise-coverage`. Outputs collected as data (raw JSON in scratchpad), not a green/red smoke.

## Aggregate

| ch | self-heal | critic coh/voice/pace/canon | critic viol | report "dropped" |
|----|-----------|-----------------------------|-------------|------------------|
| 1  | 5  | 5/2/4/2 | 3 | 5 |
| 2  | 1  | 5/5/4/5 | 0 | 3 |
| 3  | 2  | 5/5/4/5 | 0 | 3 |
| 4  | 10 | 2/4/3/5 | 1 | 2 |
| 5  | 2  | 5/5/4/5 | 0 | 2 |
| 6  | 6  | 5/5/4/5 | 0 | 2 |
| 7  | 2  | 4/5/4/5 | 0 | 5 |
| 8  | 4  | 5/5/4/5 | 0 | 0 |
| 9  | 6  | 4/4/3/2 | 3 | 3 |
| 10 | 4  | 4/5/4/2 | 2 | 0 |
| 11 | 1  | 5/5/4/5 | 0 | 2 |
| 12 | 6  | 5/5/4/4 | 1 | 3 |
| **Σ** | **49** | avg 4.5/4.6/3.8/4.2 | **10** | **30** |

**Book promise-coverage (v2, spec-anchored):** tracked=10 · paid=3 · progressing=7 · **abandoned=0 · absent=0**.

## Signal vs noise, per surface

**① Critic (4-dim) — highest trust. Keep as-is.** All 10 violations are REAL convention breaks:
ông/Bà/mẫu thân-ngươi (ch1), a genuine repetition LOOP the critic named "looping" (ch4), Bà-ta/Lão-ta/
Lão-nhân (ch9), hắn-for-Lâm-Tử-Hàn + direct-speech self-reference (ch10), ông-for-Lâm-Chấn-Nhạc (ch12).
Zero false positives. `canon_consistency` is a reliable proxy for xưng-hô violations (every canon≤2 chapter
has ≥2 violations). The low `coherence` at ch4 (=2) correctly flags a broken draft.

**② Self-heal — good, but the objective fixes are buried.** 49 proposals, **0 no-ops** (the code no-op filter
works). By type: ADDRESS/HONORIFIC ×15, REPEATED-INFORMATION ×15, LOGIC/CAUSE-EFFECT ×14, plus a few
phrasing/typo/contradiction. BUT **every proposal is `semantic` tier** → with the re-ranker OFF (default),
NONE are pre-checked. The 15 honorific fixes are objective RULE edits (the type-routed re-ranker would
auto-tick them) yet sit unchecked among subjective trims. The code *deterministic* pronoun prefilter isn't
catching them — the LLM proposes richer context spans than the whole-word swap the prefilter matches.

**③ Per-chapter "dropped promises" — a FALSE-POSITIVE MACHINE. The loudest noise.** The per-chapter report
flags **30 "dropped"** promises across 12 chapters — but the book-level v2 coverage says **abandoned = 0**.
The samples expose why: ch2 *"…(chưa thấy đối thủ xuất hiện lại)"* = "opponent hasn't reappeared **yet**",
ch5 *"chỉ mới là sự lo ngại, chưa có đối đầu trực tiếp"* = "only concern so far, no confrontation **yet**".
These are **still-progressing** threads mislabeled **dropped**. Root cause: the Quality Report reuses v1
`audit_promises` (chapter-scoped, "dropped = not-paid-within-this-text"), which in a serialized novel — where
almost every setup pays off LATER — cries wolf on nearly every open thread. The v2 book coverage, which
distinguishes *progressing* from *abandoned*, correctly reports 0 abandoned.

**④ Book promise-coverage (v2) — trustworthy after the windowing fix.** tracked=10, 3 paid / 7 progressing /
0 abandoned / 0 absent — a sensible read of a setup-heavy opening. Note run-to-run variance (an earlier probe
saw 0 paid vs this run's 3): a promise's verdict can flip paid↔progressing across runs (model non-determinism
at temp 0 on the merge). Advisory-acceptable.

## Ranked improvement backlog

1. **HIGH — reframe the per-chapter promise signal (kill the 30 false "dropped").** The per-chapter
   `audit_promises` "dropped" list is systematically wrong on serialized fiction (30 flagged vs 0 truly
   abandoned book-wide) and undermines trust in the whole report. Fix: relabel it **"open threads raised in
   this chapter"** (informational, not a defect) and let the **book-level coverage** own the paid/abandoned
   verdict — or swap the per-chapter call to the v2 progressing/abandoned semantics. `D-QUALITY-DROPPED-FP`.
2. **MED — surface the objective honorific fixes as pre-checked.** 15/49 self-heal proposals are objective
   RULE (xưng-hô) edits arriving un-pre-checked because they're `semantic` + the re-ranker is OFF. Options:
   quantify the rerank-ON benefit (re-run the eval with `rerank=true` — it's $0 on the local model), widen the
   deterministic pronoun prefilter to catch context spans, or default the type-routed re-ranker ON for local
   models. `D-QUALITY-HONORIFIC-PRECHECK`.
3. **MED — consolidate critic-violations ↔ self-heal honorific proposals (same issue, shown twice).** The
   critic's 10 canon violations and self-heal's 15 ADDRESS/HONORIFIC edits are largely the same underlying
   errors surfaced as a diagnostic AND an edit. Link them in the Polish gate: "critic flags N canon
   violations here → self-heal proposes these fixes." `D-QUALITY-CRITIC-HEAL-LINK`.
4. **LOW (not a tool fix) — ch4's draft is broken (repetition loop).** Both critic (coh=2, "looping") and
   self-heal (10 "repeated information") correctly caught a duplicated-content draft. Regenerate ch4; this is
   a generation defect, and evidence the tools detect broken drafts.
5. **LOW — book-coverage verdict variance.** paid↔progressing can flip run-to-run. Stabilize later with a
   small multi-sample vote if it matters (cost); advisory for now. `D-QUALITY-COVERAGE-VARIANCE`.

**Headline:** the critic and book-coverage surfaces are trustworthy; self-heal is good but hides its
objective wins; the per-chapter dropped-promises is the one actively-misleading surface and is the #1 fix.
