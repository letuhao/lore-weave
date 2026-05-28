import { describe, expect, it } from 'vitest';
import { spriteForPlacement } from '@/game/render/object-overlay';

// V1.2 Batch 2.1: assert every (kind, biome_object_type) tuple maps to
// the expected sprite tier + texture key. Mirrors the spec table in
// `docs/specs/2026-05-24-v1-tilemap-viewer-scope-expansion.md`.

describe('object-overlay spriteForPlacement', () => {
  it('town → Tier-XL castle', () => {
    const m = spriteForPlacement('town', undefined);
    expect(m.tier).toBe('xl');
    expect(m.textureKey).toBe('prop-xl-town');
    expect(m.displayPx).toBe(384);
  });

  it('landmark → Tier-XL statue', () => {
    const m = spriteForPlacement('landmark', undefined);
    expect(m.tier).toBe('xl');
  });

  it('mine → Tier-L', () => {
    const m = spriteForPlacement('mine', undefined);
    expect(m.tier).toBe('l');
    expect(m.displayPx).toBe(256);
  });

  it('monolith → Tier-L', () => {
    expect(spriteForPlacement('monolith', undefined).tier).toBe('l');
  });

  it('treasure → Tier-S', () => {
    const m = spriteForPlacement('treasure', undefined);
    expect(m.tier).toBe('s');
    expect(m.textureKey).toBe('prop-s-treasure_pile');
  });

  it('monster_lair → Tier-Marker skull', () => {
    const m = spriteForPlacement('monster_lair', undefined);
    expect(m.tier).toBe('marker');
    expect(m.textureKey).toBe('marker-monster_lair');
  });

  it('ferry → Tier-Marker boat', () => {
    expect(spriteForPlacement('ferry', undefined).textureKey).toBe('marker-ferry');
  });

  it('decoration → Tier-XS', () => {
    expect(spriteForPlacement('decoration', undefined).tier).toBe('xs');
  });

  it('obstacle.mountain → Tier-M rock', () => {
    const m = spriteForPlacement('obstacle', 'mountain');
    expect(m.tier).toBe('m');
    expect(m.textureKey).toBe('prop-m-mountain_rocks');
  });

  it('obstacle.tree → Tier-S tree', () => {
    const m = spriteForPlacement('obstacle', 'tree');
    expect(m.tier).toBe('s');
    expect(m.textureKey).toBe('prop-s-tree');
  });

  it('obstacle.plant → Tier-S bush', () => {
    expect(spriteForPlacement('obstacle', 'plant').textureKey).toBe('prop-s-bush');
  });

  it('obstacle.structure → Tier-M siege fragment', () => {
    expect(spriteForPlacement('obstacle', 'structure').tier).toBe('m');
  });

  it('obstacle.rock → Tier-XS', () => {
    expect(spriteForPlacement('obstacle', 'rock').tier).toBe('xs');
  });

  it('obstacle.lake → Tier-Marker', () => {
    expect(spriteForPlacement('obstacle', 'lake').textureKey).toBe('marker-lake');
  });

  it('obstacle.crater → Tier-Marker', () => {
    expect(spriteForPlacement('obstacle', 'crater').textureKey).toBe('marker-crater');
  });

  it('obstacle.animal → Tier-Marker', () => {
    expect(spriteForPlacement('obstacle', 'animal').textureKey).toBe('marker-animal');
  });

  it('obstacle.other → Tier-Marker fallback', () => {
    expect(spriteForPlacement('obstacle', 'other').textureKey).toBe('marker-other');
  });

  it('obstacle with no biome_object_type → falls through to other-marker', () => {
    expect(spriteForPlacement('obstacle', undefined).textureKey).toBe('marker-other');
  });
});
