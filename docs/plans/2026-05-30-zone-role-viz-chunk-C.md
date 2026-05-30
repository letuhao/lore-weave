# Chunk C — Backend Role-Aware Decoration Bias + Xianxia Demo + Visual Goldens (TMP-Q5)

**Spec:** [`docs/specs/2026-05-30-zone-role-viz.md`](../specs/2026-05-30-zone-role-viz.md)
**Chunk A:** `ae4cd096` (BE wire shape)
**Chunk B:** `42782e3e` (FE overlay + role breakdown)
**Branch:** `mmo-rpg/zone-role-viz`
**Size:** L (8 files / 4 logic / 0 side effects)
**Goal:** Close the TMP-Q5 arc with backend role-aware decoration density bias, a per-book registry demo in `xianxia_sample.toml`, and Playwright visual regression goldens.

## Architecture

### Backend role-aware decoration density bias

```rust
const fn role_density_multiplier(role: ZoneRole) -> f32 {
    match role {
        ZoneRole::Wilderness => 1.2,
        ZoneRole::Hub => 0.7,
        ZoneRole::Forbidden => 0.0,
        ZoneRole::Sea => 0.0,
    }
}
```

Applied AFTER `target_for` computation; `target = 0` short-circuits.

### Per-book demo in xianxia_sample.toml

```toml
[registry.zone_role_colors]
wilderness = 0xfacc15
hub = 0x4ade80
forbidden = 0x9333ea
sea = 0x06b6d4
```

### Playwright visual goldens

Use `/play` + `minimal.json` (no URL-param machinery needed on this branch). Content-gate on MetadataPanel "role breakdown" summary per `feedback_visual_goldens_must_gate_on_content`.

## File list (8 files)

| # | File | Action |
|---|---|---|
| 1 | `services/tilemap-service/src/engine/modificators/decoration_placer.rs` | MOD — role multiplier |
| 2 | `services/tilemap-service/tests/decoration_placer.rs` | MOD — bias tests |
| 3 | `services/tilemap-service/registry/xianxia_sample.toml` | MOD — `zone_role_colors` |
| 4 | `services/tilemap-service/src/registry.rs` | MOD — xianxia override test |
| 5 | `frontend-game/e2e/zone-role-visual-regression.spec.ts` | NEW |
| 6 | `frontend-game/e2e/zone-role-visual-regression.spec.ts-snapshots/*.png` | NEW (auto) |
| 7 | `docs/plans/2026-05-30-zone-role-viz-chunk-C.md` | NEW |

## Invariants

1. Forbidden + Sea multiplier ×0 — defensive
2. Wilderness ×1.2, Hub ×0.7 — V1 hard-coded
3. `target_for` math unchanged — multiplier applies AFTER
4. Xianxia demo carries all 4 fields
5. Visual goldens content-gated

## Test plan

| Test | Verifies |
|---|---|
| `wilderness_1_2x_multiplier` | Bias up |
| `hub_0_7x_multiplier` | Bias down |
| `forbidden_zero_density` | ×0 defensive |
| `xianxia_sample_carries_zone_role_colors_override` | Per-book demo |
| `zone-roles-off.png` golden | Baseline |
| `zone-roles-on.png` golden | Overlay-on |
| Role breakdown content gate | Per visual_goldens_must_gate_on_content |

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Wilderness ×1.2 increases existing test counts | Bias goes UP; threshold = floor |
| Hub ×0.7 drops below threshold | Minimal.json has 1 Hub zone; verify |
| Cross-platform golden flake | Per-platform pin |
| Hard-coded multipliers feel arbitrary | Code rationale + future override deferred |
