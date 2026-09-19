# Remediation Cycle — investigate, post, fix, prove, update

**Status: ENFORCED** by [`scripts/remediation-cycle-gate.py`](../../scripts/remediation-cycle-gate.py).
Introduced 2026-09-13, at the PO's instruction: *"prepare new gate for multiple cycle loop —
investigate, post issues and fix then prove the fix work and update AC"*.

## 1. RC-1 — the rule

> **An acceptance criterion moves to `✅ met` only through a recorded cycle, and a cycle has all
> five stages: INVESTIGATE · ISSUES · FIX · PROOF · AC IMPACT.**

Meeting a bar is not the same as claiming to. The cycle is what makes the difference auditable by
someone who was not there.

## 2. Why five stages, and why none of them is optional

Each stage exists because skipping it has produced a specific, recorded failure in this repo:

| stage | what it prevents |
|---|---|
| **INVESTIGATE** | Fixing the symptom you noticed rather than the defect. Seven premises in the 2026-09-12 plan were wrong; each was corrected by looking rather than recalling, and one had a row parked as blocked for a reason that did not exist. |
| **ISSUES** | Work with no public record. A fix nobody can find is a fix nobody can review, and a defect with no issue is one that gets rediscovered. |
| **FIX** | — |
| **PROOF** | The whole reason [Non-Vacuity](./non-vacuity.md) exists. *"I fixed it"* is a claim; a check watched going red and then green is evidence. |
| **AC IMPACT** | A fix that moves no criterion did not move the bar. Without this the board fills with work while the ship question stays exactly where it was — which is the failure that created the acceptance-criteria standard in the first place. |

**The loop runs many times.** One cycle rarely meets a criterion. `🚧 partial` exists so a cycle can
record real movement without overclaiming, and the next cycle picks it up.

## 3. The shape

Cycles live under a `## Cycles` heading in the plan that owns the criteria:

```markdown
### Cycle 1 — dependency vulnerabilities

**Investigated:** every ecosystem's audit output, read rather than summarised. 4 scanners, N findings.
**Issues:** #251, #252
**Fix:** `abc1234` bumps `datasets` 2.21.0 → 5.0.1
**Proof:**

```
pip-audit: No known vulnerabilities found
EXIT=0
```

**AC impact:** AC-6 ❌ not met → 🚧 partial — the fixable half is fixed; `rsa` still needs acceptance.
```

## 4. What the gate enforces

| id | rule |
|---|---|
| **RC-1** | Every `### Cycle <n>` block carries all five fields. A missing field is a stage that did not happen. |
| **RC-2** | **Issues** names at least one `#<number>`, or says `none —` with a reason. Silence is not a reason. |
| **RC-3** | **Proof** contains a fenced block. Prose describing a result is not the result. |
| **RC-4** | **AC impact** names at least one `AC-<n>`. A cycle that moves no criterion says so explicitly. |
| **RC-5** | Every criterion at `✅ met` is named by some cycle's **AC impact**, or carries its evidence from before the cycle log existed. |
| **RC-6** | Cycle numbers are unique and ascending. A re-used number overwrites history. |

## 5. What this is NOT

**Not a replacement for the board.** Rows are still how work is tracked. A cycle is how a *bar move*
is justified, and the two are different: many rows can serve one cycle, and a cycle can move nothing.

**Not a promise that a cycle succeeds.** A cycle whose AC impact is *"AC-9 ❌ → ❌, the journey still
fails, here is why"* is a complete and valuable cycle. The gate asks for the five stages, not for
good news.
