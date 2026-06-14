# Plan — world-gen debt cleanup

> After the parameterization arc (P1–P8b) and the elevation arc (S1–S6) both
> closed, the remaining world-gen debt is small and none is load-bearing. This
> consolidates it into ordered, independently-shippable cleanup items. Each is a
> full 12-phase cycle + `/review-impl` + PO POST-REVIEW (sizes are small).

## Inventory recap (where the debt lives)

The central `docs/deferred/DEFERRED.md` has **nothing for the world-gen crate** (it
tracks the MMO engine). World-gen debt lives in the GEO handoff + specs + inline
comments. Full review: this session's audit.

---

## C1 — Dead-param + stale-comment sweep  (size **S**, byte-identical)

**Closes `D-S5-DEAD-RELIEF-PARAMS` + stale-comment debt.**

- **Remove the 7 inert `ReliefParams` fields** retired by S5's coupled rewrite:
  `tect_belt_lift`, `tect_range_weight`, `tect_uplift_lo`, `tect_uplift_hi`,
  `interior_rugged_cap`, `rugged_freq`, `tec_hill_weight`. Drop from the struct,
  `Default`, `resolved`, and the two tests that still reference them
  (`relief_params_clamp_no_panic` sets `tect_range_weight`; check
  `relief_and_ocean_depth_knobs_scale` — already retargeted to `couple_uplift_rate`
  in S5).
- **serde safety:** removing fields is back-compat — serde ignores unknown keys,
  so old `--config` JSONs still load (the removed keys are simply dropped).
  `dump-config` output shrinks (correct — they did nothing).
- **Byte-identical invariant (the safety check):** these fields are inert (S5
  stopped reading them), so removing them must NOT change generation or render
  output. **Verify the 3 content pins + 8 render pins still hold** — if any trips,
  a field wasn't actually dead and we stop.
- **Fix stale comments:** `climate.rs:164`, `creative_seed.rs:72`, `params.rs:98`
  still say "DEFERRED #045" — #045 (v2 seasonality) **shipped**; update to
  reflect that. `plates.rs:538` "deferred to S4" — S4 **shipped**; update.
- **Risk:** low. Verification gate = the existing pins (byte-identical) + full suite.

## C2 — Cross-platform golden hash  (size **M**) — NEEDS PO DECISION

**Closes `D-WORLDGEN-XPLATFORM-GOLDEN`** (`flatworld.rs:1470-1478`): the flatworld
golden hashes are `#[ignore]`d in CI because raw `f32` bit patterns aren't
deterministic cross-platform; the fix is to **quantize the field to fixed-point
before hashing**, rebaseline, and re-enable.

⚠ **Tension with the frozen-flat-track rule.** `flatworld.rs` is part of the
frozen flat track (must not be touched). The fix is **test-only** (quantize in the
test before hashing — no production-behavior change), but it still edits a frozen
file's test module. Also the flat track is a **standalone paused experiment**, not
the production sphere path — so the value of re-enabling its xplatform CI gate is
debatable. **Two options for the PO:**
- **(a) Fix it** — test-only quantize-before-hash + rebaseline + re-enable in CI
  (restores test integrity; touches frozen test code with explicit sign-off).
- **(b) Won't-fix / document** — accept the `#[ignore]` as deliberate for a frozen
  experimental track; downgrade the row to "won't-fix" with a one-line rationale.
- **Recommendation:** (b) unless the flat track is going back into active use —
  spending an M on a frozen experiment's CI gate is low ROI.

## C3 — Orphan service cleanup  (size **S**) — NEEDS PO DECISION + COORDINATION

**Closes `D-WORLD-TRAVEL-DOMAIN` (DEFERRED 079, the world-gen-relevant slice).**
`services/world-service` + `services/travel-service` are Cycle-5 scaffold binaries
**superseded by `crates/world-gen`** (GEO §1). They're orphans.

⚠ **Outside the world-gen crate** — deleting them touches monorepo config:
`contracts/language-rule.yaml` (the lint FAILs on a present service with no row /
mapped `missing`), `infra/docker-compose*`, CI matrices, any workspace member
list. **Options:**
- **(a) Delete** both service dirs + scrub every reference (language-rule row,
  compose, CI). Clean but cross-cutting; verify `language-rule-lint.sh` passes.
- **(b) Keep + annotate** — leave a `DEPRECATED.md` in each pointing at
  `crates/world-gen`, keep the language-rule rows.
- **Recommendation:** (a) if we want a clean tree, but schedule it as its own
  task (it's a monorepo-config change, not a world-gen change) so it doesn't
  muddy the generator's git history.

## Optional / deferred (not scheduled — product/visual calls)

- **P2 follow-up** — param-ize the Profile-mode-only literals (`height_at`
  smoothstep gates, `apply_falloff` coastline constants). Legacy single-continent
  path; low value.
- **P3 follow-up** — param-ize moisture-transport consts + `ClimateZone::wetness`
  / `bias_delta` tables.
- **Climate #047** — Dfa/Dfb→Temperate mapping (more temperate plains); needs a
  visual eval + PO choice.
- **`continent_latitude_spread` default** — now #045/#046 shipped, consider
  flipping the default on (needs a biome-proportion sweep first).
- These stay in the GEO handoff Deferred list until chosen.

## Out of scope (design boundary — NOT debt)

Elevation spec §5: time-stepped plate simulation, mantle convection, sediment
stratigraphy, glacial/aeolian erosion, sea-level eustasy. `world_archetype`-driven
terrain (GEO-D7 / V2). The flatworld bottom-up track's own roadmap (lakes/delta,
TerrainTile LOD, cross-plate seams, persistence).

## Suggested order

1. **C1** now (cheap, byte-identical, pure win — removes dead surface + stale docs).
2. **C2 / C3** only after the PO picks (a) vs (b) — both have a frozen-track /
   cross-cutting caveat that makes "just do it" the wrong default.
3. Viewer = separate track (placement under discussion — see the session thread).
