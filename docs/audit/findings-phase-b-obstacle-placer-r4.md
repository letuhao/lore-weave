# Adversary Design Review — Phase B: ObstaclePlacer + Biomes (round 4)

**Verdict: REJECTED** — 1 BLOCK + 2 WARN. (Sub-agent file-write policy-blocked; persisted by the orchestrator. AUDIT_LOG.jsonl round-4 event appended by the sub-agent.) r1/r2/r3 BLOCKs confirmed resolved.

## Finding 1 — BLOCK — AC-5 verifies erosion with a `connected_components` count delta
- **Location:** spec AC-5.
- **Problem:** D5's erosion *gate* correctly uses `would_seal_a_gap` (split-or-eliminate), but AC-5 — the property test that *verifies* D5 — asserts a raw `connected_components` count delta. Splitting one component while eliminating another leaves the count unchanged (`connectivity.rs` has a test proving exactly this), so AC-5 is false-green for the one connectivity-critical step in the phase.
- **Fix:** AC-5 — assert `would_seal_a_gap(all-eroded-tiles, pre_erosion_passable) == false` + an independent all-pairs reachability property test; drop `connected_components`.

## Finding 2 — WARN — D7/AC-7 overclaim river discovery
- **Location:** spec D7, AC-7; TMP_005 §4.5.
- **Problem:** `TilemapObjectPlacement` stores only `anchor`, not the footprint; TMP_005 §4.5 passes a placed object's *area* to RiverPlacer. D7's "Phase E reads it / discovery works" presents an unsolved forward dependency as solved.
- **Fix:** D7/AC-7 — soften: Phase B's contract is the `biome_object_type` tag; whether Phase E needs the footprint extent (an additive change) is a Phase-E decision. Log a Deferred item.

## Finding 3 — WARN — AC-10 carries the count-delta oracle forward to Phase C
- **Location:** spec AC-10.
- **Problem:** AC-10's "no more fragmented" is the same raw-count framing as AC-5; the spec defends it as vacuous-for-Phase-B but concedes it goes live (wrong) in Phase C.
- **Fix:** AC-10 — state in split-OR-eliminate / reachability terms now, so it is correct when Phase C activates it.

---
Captured rules: read pre-loaded; Guardrails relevant: no — `check_guardrails` returned `pass:true`.

**Resolution (orchestrator, 2026-05-17):** AC-5 — split-OR-eliminate oracle (`would_seal_a_gap` over the total eroded mask) + independent all-pairs reachability property test, count delta dropped. D7 + AC-7 — river-discovery claim softened to the `biome_object_type` tag; footprint-extent is a Phase-E decision (Deferred). AC-10 — restated in split-OR-eliminate / reachability terms. Re-review at round 5.
