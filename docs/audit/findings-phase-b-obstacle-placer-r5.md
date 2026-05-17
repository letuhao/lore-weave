# Adversary Design Review — Phase B: ObstaclePlacer + Biomes (round 5, final)

**Verdict: APPROVED_WITH_WARNINGS** — 0 BLOCK + 3 WARN. (Sub-agent file-write policy-blocked; persisted by the orchestrator. AUDIT_LOG.jsonl round-5 event appended by the sub-agent.) Rounds 1-4 hardened the connectivity machinery, the xor two-coin model, the golden rebaseline, and the river-discovery scoping — all sound, not re-litigated.

## WARN-1 — AC-1 demanded a Water `Tree` biome TMP_005 §6 omits
- **Location:** spec AC-1, D2; TMP_005 §6.
- **Problem:** AC-1 asserted all 8 surface terrains (incl. `Water`) covered by a `Tree` biome; §6's Water row lists the Tree cell as "(none)". AC-1 was false-red against a §6-faithful library.
- **Fix:** AC-1 — `Tree`/`Mountain`/`Rock`/`Plant` coverage scoped to the 7 land terrains; `Water` covered by `Mountain`/`Rock`/`Plant` only (no `Tree`; a Sea zone's `Tree` rule takes the §9 Q3 fallback).

## WARN-2 — D2/AC-1 fixed template count at 2-4; TMP_005 §1+§2.1 mandate 4-10
- **Location:** spec D2, AC-1; TMP_005 §1, §2.1.
- **Problem:** §2.1 pins a `BiomeSet` at 4-10 templates; the spec shipped 2-4 and AC-1 enforced the deviation.
- **Fix:** D2 — V1+30d library ships 4-6 templates per set (the compact end of §2.1's 4-10); AC-1 asserts 4-10.

## WARN-3 — AC-5's "2-wide edge corridor must erode to 1-wide" under-specified
- **Location:** spec AC-5.
- **Problem:** Holds for a *connective* corridor; a 2-wide *dead-end appendage* erodes fully to 0-wide. AC-5 left the topology ambiguous.
- **Fix:** AC-5 — name both fixtures: a sole-link 2-wide corridor erodes to 1-wide (never sealed); a 2-wide dead-end appendage erodes away fully.

---
Captured rules: read pre-loaded; Guardrails relevant: no — `check_guardrails` returned `pass:true`.

**Resolution (orchestrator, 2026-05-17):** all 3 WARN folded into the spec — AC-1 (land vs Water coverage; 4-10 template count), D2 (4-6 templates, Water has no Tree), AC-5 (both corridor topologies named). Design review closed APPROVED_WITH_WARNINGS after 5 rounds.
