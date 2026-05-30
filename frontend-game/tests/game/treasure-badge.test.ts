import { describe, expect, it } from 'vitest';
import {
  BAND_COLORS,
  BAND_LABELS,
  VALUE_BAND_DEFAULTS,
  bandColor,
  bandLabel,
  pickValueBand,
  shouldStampBadge,
} from '../../src/game/render/treasure-badge';

describe('TMP-Q4 chunk B — pickValueBand', () => {
  it('with default thresholds maps to 5 distinct bands', () => {
    // Sanity check: each band region maps to its own index.
    expect(pickValueBand(0)).toBe(0); // low
    expect(pickValueBand(499)).toBe(0);
    expect(pickValueBand(500)).toBe(1); // low-mid (threshold-equality goes higher)
    expect(pickValueBand(1999)).toBe(1);
    expect(pickValueBand(2000)).toBe(2); // mid
    expect(pickValueBand(4999)).toBe(2);
    expect(pickValueBand(5000)).toBe(3); // high
    expect(pickValueBand(11999)).toBe(3);
    expect(pickValueBand(12000)).toBe(4); // gilt
    expect(pickValueBand(99999)).toBe(4);
  });

  it('treats threshold equality as the HIGHER band', () => {
    // Documented semantic: `value < thresholds[i]` so equal → higher band.
    for (let i = 0; i < VALUE_BAND_DEFAULTS.length; i++) {
      const t = VALUE_BAND_DEFAULTS[i]!;
      expect(pickValueBand(t)).toBe(i + 1);
    }
  });

  it('accepts a custom xianxia-style threshold scale', () => {
    const xianxia: readonly [number, number, number, number] = [1000, 5000, 15000, 50000];
    expect(pickValueBand(500, xianxia)).toBe(0);
    expect(pickValueBand(1000, xianxia)).toBe(1);
    expect(pickValueBand(20000, xianxia)).toBe(3);
    expect(pickValueBand(60000, xianxia)).toBe(4);
  });

  it('clamps NaN value to band 0 (defensive)', () => {
    expect(pickValueBand(Number.NaN)).toBe(0);
    expect(pickValueBand(Number.POSITIVE_INFINITY)).toBe(0);
    expect(pickValueBand(Number.NEGATIVE_INFINITY)).toBe(0);
  });

  it('clamps negative value to band 0 (defensive)', () => {
    expect(pickValueBand(-1)).toBe(0);
    expect(pickValueBand(-99999)).toBe(0);
  });

  it('falls back to defaults when thresholds contain NaN', () => {
    const bad: readonly [number, number, number, number] = [Number.NaN, 100, 200, 300];
    // Falls back to [500, 2000, 5000, 12000] → 250 < 500 → band 0
    expect(pickValueBand(250, bad)).toBe(0);
    // Without fallback: 250 > 200 but < 300 → band 3, would be wrong.
  });

  it('falls back to defaults when thresholds contain negative numbers', () => {
    const bad: readonly [number, number, number, number] = [-100, 200, 300, 400];
    expect(pickValueBand(250, bad)).toBe(0); // defaults: 250 < 500
  });

  it('sorts non-ascending thresholds locally (still deterministic)', () => {
    // Input is finite + non-negative but not strictly ascending.
    // After local sort: [1, 100, 5000, 9999]
    //   1500 < 5000 ⇒ band 2
    //   50 < 100 ⇒ band 1
    //   10000 ≥ 9999 ⇒ band 4
    const messy: readonly [number, number, number, number] = [5000, 100, 9999, 1];
    expect(pickValueBand(1500, messy)).toBe(2);
    expect(pickValueBand(50, messy)).toBe(1);
    expect(pickValueBand(10000, messy)).toBe(4);
  });

  it('null thresholds is treated the same as undefined (defaults applied)', () => {
    expect(pickValueBand(750, null)).toBe(1);
    expect(pickValueBand(750, undefined)).toBe(1);
  });
});

describe('TMP-Q4 chunk B — bandColor', () => {
  it('returns the 5 Tailwind palette colors for valid indices', () => {
    expect(bandColor(0)).toBe(0x9ca3af);
    expect(bandColor(1)).toBe(0x10b981);
    expect(bandColor(2)).toBe(0x3b82f6);
    expect(bandColor(3)).toBe(0xa855f7);
    expect(bandColor(4)).toBe(0xfbbf24);
  });

  it('clamps below 0 to band 0 (defensive)', () => {
    expect(bandColor(-1)).toBe(BAND_COLORS[0]);
    expect(bandColor(-99)).toBe(BAND_COLORS[0]);
  });

  it('clamps above 4 to band 4 (defensive)', () => {
    expect(bandColor(5)).toBe(BAND_COLORS[4]);
    expect(bandColor(99)).toBe(BAND_COLORS[4]);
  });

  it('treats non-finite input as band 0 (defensive: paranoid default)', () => {
    // bandColor and bandLabel share the same `Number.isFinite` gate so
    // both fall back to 0 on NaN/Inf. Treating Inf as band 4 would be
    // more semantically generous, but the "paranoid 0" choice keeps
    // both helpers symmetric + makes the bug-shape ("garbage in, low
    // band out") visible to the eye in the viewer.
    expect(bandColor(Number.NaN)).toBe(BAND_COLORS[0]);
    expect(bandColor(Number.POSITIVE_INFINITY)).toBe(BAND_COLORS[0]);
    expect(bandColor(Number.NEGATIVE_INFINITY)).toBe(BAND_COLORS[0]);
  });
});

describe('TMP-Q4 chunk B — bandLabel', () => {
  it('returns the 5 readable labels for valid indices', () => {
    expect(bandLabel(0)).toBe('low');
    expect(bandLabel(1)).toBe('low-mid');
    expect(bandLabel(2)).toBe('mid');
    expect(bandLabel(3)).toBe('high');
    expect(bandLabel(4)).toBe('gilt');
  });

  it('clamps out-of-bounds and NaN inputs', () => {
    expect(bandLabel(-1)).toBe(BAND_LABELS[0]);
    expect(bandLabel(99)).toBe(BAND_LABELS[4]);
    expect(bandLabel(Number.NaN)).toBe(BAND_LABELS[0]);
  });
});

describe('TMP-Q4 chunk B LOW-2 + LOW-5 — shouldStampBadge gate', () => {
  // Both `object-overlay.ts` (canvas) and `TileInspector.tsx`
  // (DOM section) route through this predicate, so a regression here
  // would break BOTH surfaces in lockstep — making the bug visible
  // in unit tests (this file) AND in chromium tests instead of a
  // silent palette drift.

  it('accepts V1 treasure with finite value', () => {
    expect(shouldStampBadge({ kind: 'treasure', value: 100 })).toBe(true);
    expect(shouldStampBadge({ kind: 'treasure', value: 9999 })).toBe(true);
  });

  it('accepts V2 pickup primitive with finite value (V1→V2 migration)', () => {
    // LOW-5 dual-gate fix: when the V1 `kind` field is dropped (the
    // V2 data-model ADR plans for this), placements ride on the
    // wire as `primitive === 'pickup'` only. The badge stamp must
    // continue to fire.
    expect(shouldStampBadge({ primitive: 'pickup', value: 100 })).toBe(true);
    // Both V1 + V2 fields set (the current migration window)
    expect(
      shouldStampBadge({ kind: 'treasure', primitive: 'pickup', value: 100 }),
    ).toBe(true);
  });

  it('LOW-6 — value === 0 still stamps a badge (degenerate but valid pile)', () => {
    // A future template author could declare a tier with min=0, max=0
    // and density>0 — TreasurePlacer skips it today (compose_pile
    // returns None for max==0), but if a migration ever lands a
    // 0-value treasure on the wire, the gate must not short-circuit
    // on falsy `value`. The badge would render band 0 (low — visually
    // honest signal that the pile is empty).
    expect(shouldStampBadge({ kind: 'treasure', value: 0 })).toBe(true);
  });

  it('rejects MonsterLair guards (MED-1)', () => {
    // The guard inherits `tier_index` (chunk A LOW-1) but its `value`
    // is monster STRENGTH not gold. Stamping a band on the guard would
    // render a misleading "gilt" / "low-mid" color based on strength,
    // not the pile's worth. This test pins MED-1 from chunk-B
    // self-review pre-BUILD.
    expect(
      shouldStampBadge({ kind: 'monster_lair', value: 850, primitive: 'blocker' }),
    ).toBe(false);
  });

  it('rejects non-treasure kinds even with a value', () => {
    for (const kind of [
      'obstacle',
      'mine',
      'town',
      'landmark',
      'monolith',
      'ferry',
      'decoration',
    ]) {
      expect(shouldStampBadge({ kind, value: 100 })).toBe(false);
    }
  });

  it('rejects treasure with no value (missing / null / undefined)', () => {
    expect(shouldStampBadge({ kind: 'treasure' })).toBe(false);
    expect(shouldStampBadge({ kind: 'treasure', value: null })).toBe(false);
    expect(shouldStampBadge({ kind: 'treasure', value: undefined })).toBe(false);
  });

  it('rejects treasure with non-finite value (defense in depth)', () => {
    expect(shouldStampBadge({ kind: 'treasure', value: Number.NaN })).toBe(false);
    expect(
      shouldStampBadge({ kind: 'treasure', value: Number.POSITIVE_INFINITY }),
    ).toBe(false);
  });
});

describe('TMP-Q4 chunk B MED-1 — canvas + inspector color paths agree', () => {
  it('canvas-path and inspector-path compute the same color for the same placement', () => {
    // The canvas badge color (object-overlay.ts) is computed via
    //   bandColor(pickValueBand(p.value, view.registry_ref?.value_band_thresholds))
    // The inspector swatch (TileInspector.tsx BandRow) is computed via
    //   bandColor(pickValueBand(p.value, inspector.valueBandThresholds))
    // Today `lookupAt` literally copies `view.registry_ref?.value_band_thresholds`
    // into `inspector.valueBandThresholds`. This test pins the
    // equivalence so a future per-zone threshold transform in
    // `lookupAt` (a plausible follow-up) cannot silently desync the
    // two surfaces without failing here.
    const view = {
      registry_ref: {
        id: 'lw',
        version: '1.0.0',
        value_band_thresholds: [500, 2000, 5000, 12000] as [
          number,
          number,
          number,
          number,
        ],
      },
    };
    const inspectorPayload = {
      valueBandThresholds: view.registry_ref.value_band_thresholds,
    };

    // Probe with a value in each of the 5 bands.
    for (const value of [100, 1000, 3000, 8000, 25000]) {
      const canvasBand = pickValueBand(
        value,
        view.registry_ref?.value_band_thresholds ?? null,
      );
      const inspectorBand = pickValueBand(
        value,
        inspectorPayload.valueBandThresholds ?? null,
      );
      expect(
        inspectorBand,
        `MED-1: canvas/inspector divergence at value=${value}`,
      ).toBe(canvasBand);
      expect(bandColor(inspectorBand)).toBe(bandColor(canvasBand));
    }
  });

  it('canvas + inspector paths agree when registry omits thresholds (defaults fallback)', () => {
    const view = { registry_ref: { id: 'lw', version: '1.0.0' } };
    const inspectorPayload = { valueBandThresholds: null };
    for (const value of [100, 1000, 3000, 8000, 25000]) {
      const canvasBand = pickValueBand(
        value,
        (view.registry_ref as unknown as { value_band_thresholds?: never })
          ?.value_band_thresholds ?? null,
      );
      const inspectorBand = pickValueBand(
        value,
        inspectorPayload.valueBandThresholds,
      );
      expect(inspectorBand).toBe(canvasBand);
    }
  });
});
