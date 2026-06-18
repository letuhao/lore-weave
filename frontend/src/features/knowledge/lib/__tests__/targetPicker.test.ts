import { describe, expect, it } from 'vitest';
import {
  ALL_TARGETS,
  canonicalTargets,
  entitiesExplicitlyRequested,
  isAutoIncluded,
  resolveTargets,
} from '../targetPicker';

describe('canonicalTargets (wire payload — NO entities auto-include)', () => {
  it('empty ⇒ []', () => {
    expect(canonicalTargets([])).toEqual([]);
  });

  it('relations stays relations (entities added at runtime, not here)', () => {
    expect(canonicalTargets(['relations'])).toEqual(['relations']);
  });

  it('events stays events', () => {
    expect(canonicalTargets(['events'])).toEqual(['events']);
  });

  it('dedups + canonical order without injecting entities', () => {
    expect(canonicalTargets(['facts', 'events', 'events'])).toEqual([
      'events',
      'facts',
    ]);
  });
});

describe('resolveTargets (C12 dependent auto-include)', () => {
  it('empty selection returns [] (caller omits ⇒ BE runs all)', () => {
    expect(resolveTargets([])).toEqual([]);
  });

  it('entities only stays entities', () => {
    expect(resolveTargets(['entities'])).toEqual(['entities']);
  });

  it('relations auto-includes entities, canonical order', () => {
    expect(resolveTargets(['relations'])).toEqual(['entities', 'relations']);
  });

  it('events auto-includes entities', () => {
    expect(resolveTargets(['events'])).toEqual(['entities', 'events']);
  });

  it('summaries alone does NOT force entities', () => {
    expect(resolveTargets(['summaries'])).toEqual(['summaries']);
  });

  it('dedups and orders canonically', () => {
    expect(resolveTargets(['facts', 'facts', 'events', 'entities'])).toEqual([
      'entities',
      'events',
      'facts',
    ]);
  });

  it('covers the full taxonomy in canonical order', () => {
    expect(resolveTargets(ALL_TARGETS)).toEqual(ALL_TARGETS);
  });
});

describe('isAutoIncluded', () => {
  it('entities is auto-included when a dependent target is selected', () => {
    expect(isAutoIncluded('entities', ['relations'])).toBe(true);
    expect(isAutoIncluded('entities', ['events'])).toBe(true);
  });

  it('entities is NOT auto-included when chosen explicitly', () => {
    expect(isAutoIncluded('entities', ['entities', 'relations'])).toBe(false);
  });

  it('entities is NOT auto-included for summaries-only', () => {
    expect(isAutoIncluded('entities', ['summaries'])).toBe(false);
  });

  it('non-entity targets are never auto-included', () => {
    expect(isAutoIncluded('relations', ['relations'])).toBe(false);
  });
});

describe('entitiesExplicitlyRequested (recovery/filter gate)', () => {
  it('empty ⇒ all passes ⇒ enabled', () => {
    expect(entitiesExplicitlyRequested([])).toBe(true);
  });

  it('explicit entities ⇒ enabled', () => {
    expect(entitiesExplicitlyRequested(['entities', 'events'])).toBe(true);
  });

  it('events-only (no explicit entities) ⇒ disabled', () => {
    expect(entitiesExplicitlyRequested(['events'])).toBe(false);
  });
});
