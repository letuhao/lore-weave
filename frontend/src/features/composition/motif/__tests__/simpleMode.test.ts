// W6 §7.1 — simpleMode pure-fn tests: tier derivation, read-only, label maps.
import { describe, expect, it } from 'vitest';
import {
  actantLabelKey, conformanceGlyph, conformanceTone, fieldLabelKey, isReadOnly,
  kindLabelKey, motifTier, tierLabelKey,
} from '../simpleMode';
import type { Actant, MotifKind } from '../types';

const ME = 'user-1';

describe('motifTier (tenancy derivation)', () => {
  it('ownerless → system', () => {
    expect(motifTier({ owner_user_id: null, visibility: 'unlisted' }, ME)).toBe('system');
  });
  it('caller owns → user', () => {
    expect(motifTier({ owner_user_id: ME, visibility: 'private' }, ME)).toBe('user');
  });
  it("someone else's public → public", () => {
    expect(motifTier({ owner_user_id: 'user-2', visibility: 'public' }, ME)).toBe('public');
  });
  it("someone else's private (visible via grant) → public grouping (not user)", () => {
    expect(motifTier({ owner_user_id: 'user-2', visibility: 'private' }, ME)).toBe('public');
  });
  it('no logged-in user → owned rows read as public (never mine)', () => {
    expect(motifTier({ owner_user_id: 'user-2', visibility: 'public' }, null)).toBe('public');
  });
});

describe('isReadOnly (clone-to-edit gate — the kinds-bug lesson)', () => {
  it('system motif is read-only', () => {
    expect(isReadOnly({ owner_user_id: null, visibility: 'unlisted' }, ME)).toBe(true);
  });
  it("another user's public motif is read-only", () => {
    expect(isReadOnly({ owner_user_id: 'user-2', visibility: 'public' }, ME)).toBe(true);
  });
  it('my own motif is editable', () => {
    expect(isReadOnly({ owner_user_id: ME, visibility: 'private' }, ME)).toBe(false);
  });
});

describe('label registries (every expert label maps to a simple label)', () => {
  const actants: Actant[] = ['subject', 'object', 'sender', 'receiver', 'helper', 'opponent'];
  const kinds: MotifKind[] = ['sequence', 'situation', 'hook', 'emotion_arc', 'trope', 'pattern', 'scheme'];

  it('every actant has distinct simple + expert keys', () => {
    for (const a of actants) {
      const simple = actantLabelKey(a, true);
      const expert = actantLabelKey(a, false);
      expect(simple).toContain('simple');
      expect(expert).toContain('expert');
      expect(simple).not.toBe(expert);
    }
  });
  it('every kind has distinct simple + expert keys', () => {
    for (const k of kinds) {
      expect(kindLabelKey(k, true)).toContain('simple');
      expect(kindLabelKey(k, false)).toContain('expert');
    }
  });
  it('field labels switch registry by mode', () => {
    expect(fieldLabelKey('tension_target', true)).toBe('motif.simple.field.tension_target');
    expect(fieldLabelKey('tension_target', false)).toBe('motif.expert.field.tension_target');
  });
  it('tier label keys are stable', () => {
    expect(tierLabelKey('system')).toBe('motif.tier.system');
    expect(tierLabelKey('user')).toBe('motif.tier.user');
    expect(tierLabelKey('public')).toBe('motif.tier.public');
  });
});

describe('conformance tone + glyph (§5.3 co-encoding)', () => {
  it('beat realized + tension match → ok ✓', () => {
    expect(conformanceTone(true, true)).toBe('ok');
    expect(conformanceGlyph('ok')).toBe('✓');
  });
  it('beat not realized → bad ✗ (worst case wins)', () => {
    expect(conformanceTone(false, true)).toBe('bad');
    expect(conformanceGlyph('bad')).toBe('✗');
  });
  it('beat realized but tension off → warn ⚠', () => {
    expect(conformanceTone(true, false)).toBe('warn');
    expect(conformanceGlyph('warn')).toBe('⚠');
  });
});
