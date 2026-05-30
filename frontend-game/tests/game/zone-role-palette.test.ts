import { describe, expect, it } from 'vitest';
import {
  ZONE_ROLE_DEFAULTS,
  ZONE_ROLE_FALLBACK,
  zoneRoleColor,
  zoneRoleLabel,
} from '../../src/game/render/zone-role-palette';

// TMP-Q5 chunk B — zone role palette resolution.
// Both `overlay-rt.ts` (canvas tint) and `role-breakdown.ts`
// (MetadataPanel swatch) route through `zoneRoleColor` so a
// regression breaks BOTH surfaces.

describe('TMP-Q5 chunk B — zoneRoleColor', () => {
  it('returns the built-in default for known roles', () => {
    expect(zoneRoleColor('wilderness')).toBe(ZONE_ROLE_DEFAULTS.wilderness);
    expect(zoneRoleColor('hub')).toBe(ZONE_ROLE_DEFAULTS.hub);
    expect(zoneRoleColor('forbidden')).toBe(ZONE_ROLE_DEFAULTS.forbidden);
    expect(zoneRoleColor('sea')).toBe(ZONE_ROLE_DEFAULTS.sea);
  });

  it('returns the fallback for unknown roles (FE 8-variant vs BE 4-variant gap)', () => {
    // The FE `ZoneRole` type allows variants the BE wire doesn't ship
    // (capital, arena, mine_camp, town). Future BE additions or
    // pre-existing FE type drift must NOT crash the renderer.
    expect(zoneRoleColor('capital')).toBe(ZONE_ROLE_FALLBACK);
    expect(zoneRoleColor('arena')).toBe(ZONE_ROLE_FALLBACK);
    expect(zoneRoleColor('totally_unknown_role_name')).toBe(ZONE_ROLE_FALLBACK);
  });

  it('uses the override when a role is declared', () => {
    const override = { wilderness: 0xff0000, hub: 0x00ff00 };
    expect(zoneRoleColor('wilderness', override)).toBe(0xff0000);
    expect(zoneRoleColor('hub', override)).toBe(0x00ff00);
  });

  it('falls back to defaults when override omits the role (sparse)', () => {
    // Only wilderness in the override; hub/forbidden/sea fall back.
    const override = { wilderness: 0xff0000 };
    expect(zoneRoleColor('wilderness', override)).toBe(0xff0000);
    expect(zoneRoleColor('hub', override)).toBe(ZONE_ROLE_DEFAULTS.hub);
    expect(zoneRoleColor('forbidden', override)).toBe(ZONE_ROLE_DEFAULTS.forbidden);
    expect(zoneRoleColor('sea', override)).toBe(ZONE_ROLE_DEFAULTS.sea);
  });

  it('LOW-1 — null override uses defaults', () => {
    // The store sets `inspector.zone_role_colors` to null when the
    // registry omits it; renderer must accept null.
    expect(zoneRoleColor('wilderness', null)).toBe(ZONE_ROLE_DEFAULTS.wilderness);
  });

  it('LOW-1 — undefined override uses defaults', () => {
    expect(zoneRoleColor('wilderness', undefined)).toBe(ZONE_ROLE_DEFAULTS.wilderness);
  });

  it('LOW-1 — non-finite override value falls through to defaults (defensive)', () => {
    // A future malformed wire could ship NaN / Infinity. Don't poison
    // the rendered Phaser fillStyle with non-finite color.
    const badOverride = {
      wilderness: Number.NaN,
      hub: Number.POSITIVE_INFINITY,
    };
    expect(zoneRoleColor('wilderness', badOverride)).toBe(ZONE_ROLE_DEFAULTS.wilderness);
    expect(zoneRoleColor('hub', badOverride)).toBe(ZONE_ROLE_DEFAULTS.hub);
  });

  it('override for an unknown role still falls through to FALLBACK', () => {
    // The override struct only types the 4 BE roles; if a future
    // override declares an unknown role (e.g., via runtime injection
    // for testing), the helper should ignore it AND return fallback
    // for that unknown role.
    const override = { wilderness: 0xff0000 } as Record<string, number>;
    expect(zoneRoleColor('totally_unknown', override)).toBe(ZONE_ROLE_FALLBACK);
  });
});

describe('TMP-Q5 chunk B — zoneRoleLabel', () => {
  it('V1 ships the raw role string', () => {
    // Future localization / pretty-printing lands here without an
    // API churn at the call sites.
    expect(zoneRoleLabel('wilderness')).toBe('wilderness');
    expect(zoneRoleLabel('sea')).toBe('sea');
  });
});

describe('TMP-Q5 chunk B MED-1 — palette identity with ZONE_CENTER_COLORS', () => {
  // MED-1 from chunk-B /review-impl — `overlay-rt.ts` carries an
  // 8-role `ZONE_CENTER_COLORS` map for the zone-center dot markers
  // (covers FE-only roles like `capital`/`arena`/`mine_camp`/`town`
  // that the BE wire doesn't ship). `zone-role-palette.ts` carries a
  // 4-role `ZONE_ROLE_DEFAULTS` map for the OVERLAY tint + panel
  // breakdown swatches.
  //
  // For the 4 BE-wire roles (wilderness/hub/forbidden/sea), BOTH
  // maps MUST carry the same hex value so the overlay tint and the
  // dot marker visibly agree per role. Without this pin, a future
  // palette tweak in one file would silently desync the surfaces.
  it('the 4 BE-wire roles share hex values across both palettes', async () => {
    const { ZONE_CENTER_COLORS } = await import(
      '../../src/game/render/overlay-rt'
    );
    expect(ZONE_CENTER_COLORS.wilderness).toBe(ZONE_ROLE_DEFAULTS.wilderness);
    expect(ZONE_CENTER_COLORS.hub).toBe(ZONE_ROLE_DEFAULTS.hub);
    expect(ZONE_CENTER_COLORS.forbidden).toBe(ZONE_ROLE_DEFAULTS.forbidden);
    expect(ZONE_CENTER_COLORS.sea).toBe(ZONE_ROLE_DEFAULTS.sea);
  });
});
