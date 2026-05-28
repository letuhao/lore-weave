# /review-impl — tilemap-service Phase C: TreasurePlacer

On-demand deep adversarial implementation review (default-mode `/review-impl`), run after the Phase-C commit `d8a27e14` at the human checkpoint. Focus: coverage gaps + drift risk — not spec-compliance (the AMAW Adversary code review already covered that).

**No HIGH (production bug).** `compose_pile`, `place_tier`, `place_guard`, `resolve_effective_tiers`, and the `place_and_connect_object` boundary were traced — all correct. 4 findings (1 MED + 3 LOW), **all fixed** in a follow-up commit.

## Finding 1 — MED — the guard-skip path had zero test coverage — FIXED

`place_guard`'s `Err(PlacementError::NoSpace) => {}` arm (D5: a guard with no non-sealing `Open` neighbour is skipped, the pile left unguarded; review r6-finding-1: a guard skip must not consume the pile loop's `emergency`) was never executed by any test — `ac4_ac6a`, `ac7`, and the determinism golden all use guard-placeable geometry where the guard always places `Ok`.

**Fix:** `guard_skipped_when_the_pile_has_no_open_neighbour` — a 3×3 zone whose centre is the sole `Open` tile (ringed by `Walkable` `free_paths`); the pile is forced dead-centre, its 4 neighbours all `Walkable`, so the guard search area is empty → guard `NoSpace` → skipped. Asserts the `Treasure` is placed and guard-eligible (value ≥ 2000) yet no `MonsterLair` accompanies it, and `process` returns `Ok`. (The deeper "guard skip never charges `emergency`" is a *structural* guarantee — `place_guard` returns `()`, so it physically cannot reach the counter — not separately tested, as an observable-divergence test would need a fragile intricate fixture.)

## Finding 2 — LOW — `compose_pile`'s `MAX_COMPOSE_ATTEMPTS` cap was unverified — FIXED

The §3.3 attempt cap never fires with the production pool (every object `value > 0` → the running sum strictly increases → the loop self-terminates first); AC-1 (`value > 0`) was the only guard.

**Fix:** `compose_pile_terminates_on_a_degenerate_zero_value_pool` — passes a hand-built pool with a sole `value: 0` object (the only construction that drives the loop to the cap, since the production pool by AC-1 cannot), asserts `compose_pile` terminates and returns `None`.

## Finding 3 — LOW — a malformed `min > max` tier was untested — FIXED

`compose_pile` with `tier.min > tier.max` returns `None` safely — but only via the empty-`RangeInclusive` semantics of `(min..=max).contains()`.

**Fix:** `compose_pile_returns_none_for_a_malformed_min_greater_than_max_tier` — pins `None` for a `min:5000, max:800` tier across 8 seeds.

## Finding 4 — LOW — `target_count` was unbounded by author input — FIXED

`target_count = (density × tiles / 1000) as u32` had no cap; a pathological author `density` (`u16`, up to 65535) on a large zone yielded a multi-million per-tier loop bound.

**Fix:** `target_count` is now `density_target.min(open_count)` — a zone cannot hold more 1×1 piles than it has `Open` tiles. The cap is **output-invariant** (it only bounds iteration count for a pathological `density`; the placed objects are identical with or without it), so it is deliberately not unit-tested — a test would be vacuous.

## Verify

`cargo test --workspace` green — 210 tilemap-service lib tests (+3 from this review) + determinism 6/6 (+1 ignored regenerator) + integration, 0 failed. `cargo clippy --workspace --all-targets` 0 warnings.
