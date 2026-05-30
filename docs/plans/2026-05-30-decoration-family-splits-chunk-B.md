# Chunk B — Per-Family Density Bias (TMP-Q6)

**Spec:** [`docs/specs/2026-05-30-decoration-family-splits.md`](../specs/2026-05-30-decoration-family-splits.md) §4 "Chunk B"
**Branch:** `mmo-rpg/decoration-family-splits` (stacks on chunk A `fef18106`)
**Size:** L (7 files / 5 logic / 1 side effect — wire-shape additive on TilemapTemplate + RegistryRef + DecorationRef extension)
**Goal:** Wire per-family density multipliers at template + registry levels. Resolution chain: template > registry > 1.0. Apply by scaling per-tag `density_weight` in `roll_weighted_tag`. No FE in this chunk — chunk C owns that.

## Architecture

### Wire-shape extensions (additive Option<HashMap>)

```rust
// services/tilemap-service/src/types/template.rs
pub struct TilemapTemplate {
    // ...existing...
    /// TMP-Q6 chunk B — per-family density multiplier override.
    /// Sparse: only families the author wants to bias appear here.
    /// Resolution: template wins per-family; absent families fall
    /// back to registry, then to 1.0. Validated at `DecorationPlacer::process`
    /// (non-finite + negative rejected; 0.0 allowed → "no decorations
    /// of this family"). Family names validated via the same regex
    /// as `ObjectKindDef.family`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub decoration_family_density: Option<HashMap<String, f32>>,
}

// services/tilemap-service/src/types/registry.rs (extend RegistryRef)
pub struct RegistryRef {
    // ...existing...
    /// TMP-Q6 chunk B — per-book per-family density baseline.
    /// Same shape + validation as TilemapTemplate's field. Resolution
    /// chain: template > registry > 1.0. Validated at `Registry::from_file`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub decoration_family_density: Option<HashMap<String, f32>>,
}
```

### `DecorationRef` denormalization

Add `family: Option<String>` to the per-biome index entry so `roll_weighted_tag` can scale weights without re-querying `Registry::get_object` per-roll.

```rust
// services/tilemap-service/src/registry.rs
pub struct DecorationRef {
    pub kind_id: String,
    pub density_weight: f32,
    pub min_spacing: u32,
    /// TMP-Q6 chunk B — denormalized from ObjectKindDef.family at
    /// from_file time so the placer's weighted roll can apply family
    /// bias without a HashMap lookup per-roll.
    pub family: Option<String>,
}
```

### Resolution chain (template > registry > 1.0)

```rust
// services/tilemap-service/src/engine/modificators/decoration_placer.rs
fn resolve_family_multiplier(
    family: Option<&str>,
    template: &TilemapTemplate,
    registry: &Registry,
) -> f32 {
    let Some(family) = family else { return 1.0 };
    if let Some(tpl) = template.decoration_family_density.as_ref() {
        if let Some(&m) = tpl.get(family) {
            return m;
        }
    }
    if let Some(reg) = registry.reference().decoration_family_density.as_ref() {
        if let Some(&m) = reg.get(family) {
            return m;
        }
    }
    1.0
}
```

### `roll_weighted_tag` signature change

```rust
fn roll_weighted_tag<'a>(
    pool: &'a [DecorationRef],
    family_mult: &impl Fn(Option<&str>) -> f32,
    rng: &mut impl rand::Rng,
) -> Option<&'a DecorationRef> { ... }
```

Returns `Option`: if every family in the pool has multiplier 0.0, `total == 0.0` and the slot is abandoned (matches "free mask exhausted" semantic). The caller breaks the slot loop on `None`.

### Validation rules

- **Family-name keys:** must match `^[a-z][a-z0-9_]*$` (same as `ObjectKindDef.family`)
- **Multiplier values:** must be finite + non-negative (0.0 IS allowed → "no decorations of this family")
- **Registry-side:** validated at `Registry::from_file` via new `validate_decoration_family_density` helper
- **Template-side:** validated at `DecorationPlacer::process` (same helper, mapped to `Error::Modificator`)

## File list (7 files)

| # | File | Action |
|---|---|---|
| 1 | `services/tilemap-service/src/types/template.rs` | MOD — `TilemapTemplate.decoration_family_density` field + tests |
| 2 | `services/tilemap-service/src/types/registry.rs` | MOD — `RegistryRef.decoration_family_density` field + builder + tests |
| 3 | `services/tilemap-service/src/registry.rs` | MOD — `DecorationRef.family` field + `validate_decoration_family_density` helper + `Registry::from_file` call site + tests |
| 4 | `services/tilemap-service/src/engine/modificators/decoration_placer.rs` | MOD — `resolve_family_multiplier` + `roll_weighted_tag` signature change + `place_in_zone` rewire + tests |
| 5 | `services/tilemap-service/tests/decoration_placer.rs` | MOD — integration tests for resolution chain + bias direction + pinned hash update |
| 6 | `services/tilemap-service/registry/default.toml` | MOD (minimal) — V2-pin sanity check; NO author bias declared in default (keeps determinism golden byte-identical absent template) |
| 7 | `docs/plans/2026-05-30-decoration-family-splits-chunk-B.md` | NEW — this plan |

**Out of chunk B (deferred to chunk C):**
- TS types extension for `decoration_family_density` (chunk C owns FE)
- HTTP integration test for wire shape (extends chunk-A scope; chunk C bundles)
- xianxia_sample.toml family bias demo (chunk C demos)
- FE breakdown helper + MetadataPanel (chunk C)
- Visual goldens (chunk C)

## Invariants

1. **V2 byte-identical preserved** when no `decoration_family_density` declared anywhere — `skip_serializing_if = "Option::is_none"` on both fields + `DecorationRef.family = None` for non-decoration objects + no behavior change in `roll_weighted_tag` when every multiplier resolves to 1.0
2. **Backward compat read** — pre-Q6 fixtures load (no field → None on both sides)
3. **Resolution chain pinned** — template wins per-family; sparse template falls back to registry per-family; fully-absent → 1.0
4. **Determinism preserved** — same `(template, seed, registry)` ⇒ byte-identical decoration list (family bias is deterministic given fixed RNG + weights)
5. **TOTAL target unchanged by bias** — multiplier rebalances the weighted POOL, not the COUNT. `density.target_for(free)` runs before bias is applied. Per AC-DFS-7.
6. **0.0 is allowed** — a multiplier of 0.0 effectively filters that family out of the pool. If every family's multiplier is 0.0, the zone gets zero decorations.
7. **Family-name validation parity** — same regex as `ObjectKindDef.family` at registry + template + validator
8. **Multiplier value validation** — non-finite + negative rejected at both layers

## Test plan

| Test | Verifies |
|---|---|
| `tilemap_template_round_trips_with_decoration_family_density_some` | Wire shape, template-side |
| `tilemap_template_skip_serializes_decoration_family_density_when_none` | V2 byte-identical, template-side |
| `tilemap_template_deserializes_pre_q6_chunk_b_fixture_without_decoration_family_density` | Backward compat, template-side |
| `registry_ref_round_trips_with_decoration_family_density` | Wire shape, registry-side |
| `registry_ref_skip_serializes_decoration_family_density_when_none` | V2 byte-identical, registry-side |
| `registry_rejects_invalid_family_name_key_in_decoration_family_density` | Registry validation reject |
| `registry_rejects_non_finite_multiplier_in_decoration_family_density` | Registry validation reject |
| `registry_rejects_negative_multiplier_in_decoration_family_density` | Registry validation reject |
| `registry_accepts_zero_multiplier_in_decoration_family_density` | 0.0 allowed |
| `decoration_ref_carries_family_after_from_file` | Denormalization works |
| `template_invalid_decoration_family_density_returns_modificator_error` | Template validation reject |
| `roll_weighted_tag_bias_up_increases_picks_of_target_family` | Bias direction (unit) |
| `roll_weighted_tag_zero_multiplier_excludes_family_from_pool` | 0.0 filtering (unit) |
| `roll_weighted_tag_returns_none_when_all_multipliers_zero` | Total=0 edge (unit) |
| `tmp_q6_template_bias_resolution_overrides_registry_per_family` | Resolution chain pinning (integration) |
| `tmp_q6_registry_bias_applied_when_template_absent` | Registry fallback (integration) |
| `tmp_q6_unbiased_decoration_distribution_unchanged_baseline` | V2 byte-identical determinism (integration; `PINNED_DECORATION_HASH` MUST stay unchanged absent a template bias) |
| `tmp_q6_family_bias_changes_decoration_tag_distribution` | AC-DFS-7 — family bias shifts the mix on identical seed |

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Determinism golden breaks because `DecorationRef.family` extension changes the index | Family field is `None` for entries without it; existing default.toml entries either all have `family` (post-chunk-A) or None. The placer only reads `family` to scale weights; if no template/registry bias is declared, multiplier is 1.0 and the weighted roll is identical to chunk A. Verify via the existing pinned-hash test. |
| Multi-zone integration test flakiness from RNG | Seeds + zones held constant across baseline + bias-up; assertion is sign-of-bias direction (counts differ), not exact magnitude. Same pattern as TMP-Q5 chunk C role-bias test. |
| Family-name normalization mismatch (TOML vs HashMap key) | Single validator function used at both layers; tests cover both the "matches ObjectKindDef.family rule" and "registry+template apply same rule" invariants |
| Empty HashMap `Some({})` emits `{}` on wire | Documented in spec; mirrors `ZoneRoleColors` `Some(empty)` discipline from TMP-Q5 chunk A. Authors should set the outer Option to None for "no override"; this is consistent precedent. |

## Out of scope (chunks A, C, future)

- Family-aware spacing rules — `min_spacing` stays per-tag
- Per-zone family bias — zone-level granularity not needed; template + registry cover it
- Combining multipliers (currently REPLACE per-family, not MERGE) — author manually multiplies if both layers needed
- FE work (chunk C)
- xianxia_sample.toml bias demo (chunk C)
- HTTP integration wire test (chunk C bundles)
