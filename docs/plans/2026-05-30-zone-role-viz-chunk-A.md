# Chunk A — Wire-Shape Foundation: `RegistryRef.zone_role_colors` (TMP-Q5)

**Spec:** [`docs/specs/2026-05-30-zone-role-viz.md`](../specs/2026-05-30-zone-role-viz.md)
**Branch:** `mmo-rpg/zone-role-viz` (fresh off main, PR #14 pending for TMP-Q3+Q4)
**Size:** M (5 BE + 1 FE + 1 doc = 7 files / 3 logic / 1 side effect = wire-shape additive)
**Goal:** Add `RegistryRef.zone_role_colors: Option<ZoneRoleColors>` with strict-typed named-field struct (matches TMP-Q4 chunk A `value_band_thresholds: Option<[u32; 4]>` precedent). Per-role colors are independently optional (sparse override allowed). Backend validation + builder parity + HTTP wire-contract test pin the contract before chunk B consumes it on the FE.

## Architecture

### Backend additive type

```rust
// services/tilemap-service/src/types/registry.rs
#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize, Deserialize)]
pub struct ZoneRoleColors {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub wilderness: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub hub: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub forbidden: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sea: Option<u32>,
}

impl ZoneRoleColors {
    /// Returns `true` iff EVERY field is `None`. Used as the
    /// `skip_serializing_if` predicate so the parent `RegistryRef`
    /// emits no key when no override is meaningful — preserving V2
    /// byte-identical wire shape.
    pub fn is_empty(&self) -> bool {
        self.wilderness.is_none()
            && self.hub.is_none()
            && self.forbidden.is_none()
            && self.sea.is_none()
    }
}
```

`RegistryRef`:
```rust
pub struct RegistryRef {
    pub id: String,
    pub version: String,
    /// TMP-Q5 — per-book role color override. Each role independently
    /// optional. When the wrapped struct is all-None OR the outer
    /// Option is None, no key on wire.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub zone_role_colors: Option<ZoneRoleColors>,
}
```

### Builder parity (chunk-A TMP-Q4 precedent)

```rust
impl RegistryRef {
    pub fn with_zone_role_colors(
        mut self,
        colors: ZoneRoleColors,
    ) -> Result<Self, ZoneRoleColorsError> {
        // V1 validation: u32 is intrinsically valid, no constraint
        // beyond TOML parse. The Result return preserves the builder-
        // validation-parity invariant from feedback memory + chunk-A
        // TMP-Q4 (so future constraints — say, alpha-bit reserved or
        // contrast-vs-foundation check — land cleanly without API
        // break).
        self.zone_role_colors = Some(colors);
        Ok(self)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ZoneRoleColorsError {
    pub detail: String,
}

impl std::fmt::Display for ZoneRoleColorsError { /* ... */ }
impl std::error::Error for ZoneRoleColorsError {}
```

### Validation at `Registry::from_file`

```rust
// Right after value_band_thresholds validation block (TMP-Q4 chunk A
// landed in PR #14; when this branch rebases, fold into one block).
if let Some(colors) = &file.registry.zone_role_colors {
    // V1: no constraint beyond TOML's u32 parse. Validation hook is
    // here so the chunk-C bias work can extend it without API churn.
    let _ = colors; // explicit no-op
}
```

### Frontend additive type

```ts
// frontend-game/src/types/tilemap.ts
export interface ZoneRoleColors {
  wilderness?: number;
  hub?: number;
  forbidden?: number;
  sea?: number;
}

export interface RegistryRef {
  id: string;
  version: string;
  /** TMP-Q5 — per-book role color override. Each role independently
   *  optional. When `undefined`, the FE falls back to
   *  ZONE_ROLE_DEFAULTS (chunk B). */
  zone_role_colors?: ZoneRoleColors;
}
```

## File list (7 files)

| # | File | Action | Lines (est) | Purpose |
|---|---|---|---|---|
| 1 | `services/tilemap-service/src/types/registry.rs` | MOD | ~50 | `ZoneRoleColors` struct + `is_empty` + `RegistryRef.zone_role_colors` field + `with_zone_role_colors` builder + `ZoneRoleColorsError` |
| 2 | `services/tilemap-service/src/registry.rs` | MOD | ~10 | Validation hook + 3 new test cases (load with colors, load without, sparse override) |
| 3 | `services/tilemap-service/tests/golden/tilemap_baseline.json` | MOD (regenerate) | wire change-aware | Golden stays byte-identical IF default registry doesn't declare colors. If it does, regenerate via `cargo test regenerate_golden_baseline -- --ignored` |
| 4 | `services/tilemap-service/tests/http_integration.rs` | MOD | ~50 | 2 new tests: `render_endpoint_emits_zone_role_colors_when_registry_declares` + `_omits_when_default_registry` |
| 5 | (RegistryFile struct test under registry.rs already covers TOML parse) | MOD | inline | Round-trip + sparse + boundary in types/registry.rs tests block |
| 6 | `frontend-game/src/types/tilemap.ts` | MOD | ~10 | `ZoneRoleColors` TS type + `RegistryRef.zone_role_colors?` |
| 7 | `docs/plans/2026-05-30-zone-role-viz-chunk-A.md` | NEW | this file | Plan doc |

## Invariants

1. **V2 byte-identical preserved when default registry omits colors** — `skip_serializing_if = Option::is_none` on both outer Option AND each field; `is_empty` helper means an all-None inner struct also skips. Existing golden bytes unchanged for the default lw registry.
2. **Sparse overrides supported** — a registry that declares only `wilderness = ...` rides the wire as `{wilderness: u32}` with no hub/forbidden/sea keys. Frontend falls back to defaults for omitted roles.
3. **Backward-compat read** — pre-Q5 fixture JSON without `zone_role_colors` round-trips via `#[serde(default)]` to None.
4. **Builder-validation-parity (`feedback_builder_validation_parity`)** — `with_zone_role_colors` returns `Result` even when V1 validation is a no-op, so future constraints land without API break.
5. **HTTP wire contract pinned end-to-end** — integration tests verify the field appears on the wire when registry declares it AND is omitted when it doesn't (matches TMP-Q4 chunk A MED-1 fix pattern).
6. **Determinism preserved** — backend pipeline reads `RegistryRef` for output; no new RNG.

## Design review findings (self-review pre-BUILD)

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| **LOW-1** | LOW | `ZoneRoleColors::is_empty` is used as `skip_serializing_if` for the OUTER Option only via `Option::is_none`; the outer Option being `Some(empty_inner)` would still emit `"zone_role_colors":{}` (cluttered wire) | Test pins: empty `ZoneRoleColors` inner struct still emits `{}` IF wrapped in Some; OR document that authors should pass None when they want no override. Document option (a): test the `{}` shape so future cleanup is intentional |
| **LOW-2** | LOW | TS type allows partial fields (`zone_role_colors: { wilderness: 0xfff }` valid), but backend round-trip preserves only declared fields. Test pin needed | Round-trip test pins sparse override |
| **LOW-3** | LOW | If PR #14 merges before this lands, the `RegistryRef` struct will have BOTH `value_band_thresholds` AND `zone_role_colors`. Rebase folds both | Note in chunk-A plan + spec; mechanical rebase |
| **COSMETIC-1** | COSMETIC | Field order in struct matters for TOML round-trip aesthetic | Place `zone_role_colors` AFTER `value_band_thresholds` (once rebased) following alphabetical-by-feature convention |

## Test plan

| Test | File | Verifies |
|---|---|---|
| `zone_role_colors_round_trips_with_all_fields` | types/registry.rs tests | Wire shape: all 4 fields set |
| `zone_role_colors_round_trips_sparse` | same | Only wilderness set; hub/forbidden/sea omitted |
| `zone_role_colors_default_is_all_none` | same | Default impl |
| `zone_role_colors_is_empty_when_all_none` | same | is_empty helper |
| `registry_ref_round_trips_with_zone_role_colors` | same | RegistryRef carries the field |
| `registry_ref_skip_serializes_when_zone_role_colors_none` | same | V2 byte-identical (outer None) |
| `registry_ref_deserializes_pre_q5_fixture_without_zone_role_colors` | same | Backward compat |
| `registry_ref_builder_with_zone_role_colors_succeeds` | same | Builder parity (Result) |
| `registry_loads_with_zone_role_colors_section` | registry.rs | TOML `[registry.zone_role_colors]` block |
| `registry_loads_without_zone_role_colors_section` | same | Backward compat at registry load |
| `registry_loads_with_sparse_zone_role_colors` | same | Sparse override |
| `render_endpoint_emits_zone_role_colors_when_registry_declares_them` | http_integration.rs | HTTP wire contract — MED-1 from chunk-A TMP-Q4 pattern |
| `render_endpoint_omits_zone_role_colors_for_default_registry` | same | V2 byte-identical on wire |

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Golden baseline change cascades through TilemapView | Default lw registry has NO override → no wire change; existing golden untouched |
| `RegistryFile` TOML parsing breaks with empty `[registry.zone_role_colors]` block | Test pin: empty block deserializes to all-None inner struct |
| `serde(default)` cascade interaction with the named-field struct | Both the wrapper Option AND each field's Option carry `#[serde(default)]` — independent defaults, no interaction |
| ZoneRoleColors hash collision with TypeScript `interface ZoneRoleColors` rename | TS field names match backend's snake_case exactly (`wilderness`, `hub`, `forbidden`, `sea`) |
| Per-book registries pre-Q5 might choke if their TOML rejects unknown keys | RegistryFile uses default serde behavior (rejects unknown keys is opt-in via `deny_unknown_fields`; the existing code does NOT use this attribute). Confirm by reading registry.rs |

## Ground-truth verification table

| Reference | File:line | Verified |
|---|---|---|
| `RegistryRef` struct | `services/tilemap-service/src/types/registry.rs:185` | YES |
| `Registry::from_file` validation hook | `services/tilemap-service/src/registry.rs:172` | YES |
| `RegistryFile.registry` TOML key | `services/tilemap-service/src/registry.rs:114` | YES |
| Builder return-Result pattern | `feedback_builder_validation_parity` memory + chunk-A TMP-Q4 | YES |
| HTTP integration test pattern | `services/tilemap-service/tests/http_integration.rs` | YES |
| Golden baseline regenerator | `cargo test regenerate_golden_baseline -- --ignored` | YES |
| `ZoneRole` 4-variant enum | `services/tilemap-service/src/types/zone.rs:16` | YES |

## Out of scope

- Backend role-aware decoration density (chunk C)
- Frontend overlay rendering + MetadataPanel breakdown (chunk B)
- Visual regression goldens (chunk C)
- Per-book demo TOML (chunk C with xianxia_sample.toml)
