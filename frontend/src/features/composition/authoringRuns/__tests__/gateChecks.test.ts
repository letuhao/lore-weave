import { describe, it, expect } from 'vitest';
import { computeGateChecks, allGateChecksPass } from '../gateChecks';

const base = {
  planStatus: 'validated' as string | null,
  scopeIds: ['ch1', 'ch2'],
  bookChapterIds: new Set(['ch1', 'ch2', 'ch3']),
  budgetUsd: 4,
  toolAllowlist: ['composition_write_prose'],
};

describe('computeGateChecks', () => {
  it('all pass on valid input', () => {
    const items = computeGateChecks(base);
    expect(allGateChecksPass(items)).toBe(true);
    expect(items.map((i) => i.id)).toEqual(['plan', 'scope', 'budget', 'allowlist']);
  });

  it('plan check fails when no plan is selected', () => {
    const items = computeGateChecks({ ...base, planStatus: null });
    expect(items.find((i) => i.id === 'plan')!.passed).toBe(false);
  });

  it('plan check fails for an unapproved plan status', () => {
    const items = computeGateChecks({ ...base, planStatus: 'proposed' });
    expect(items.find((i) => i.id === 'plan')!.passed).toBe(false);
  });

  it('plan check passes for compiled as well as validated', () => {
    expect(computeGateChecks({ ...base, planStatus: 'compiled' }).find((i) => i.id === 'plan')!.passed).toBe(true);
  });

  it('scope check fails on an empty scope', () => {
    const items = computeGateChecks({ ...base, scopeIds: [] });
    expect(items.find((i) => i.id === 'scope')!.passed).toBe(false);
  });

  it('scope check fails when a chapter is not in the book', () => {
    const items = computeGateChecks({ ...base, scopeIds: ['ch1', 'not-in-book'] });
    expect(items.find((i) => i.id === 'scope')!.passed).toBe(false);
  });

  it('scope check does not silently pass while the book chapter set is still loading (null)', () => {
    const items = computeGateChecks({ ...base, bookChapterIds: null });
    const scope = items.find((i) => i.id === 'scope')!;
    expect(scope.passed).toBe(true); // non-empty scope, membership unverified — not a hard fail
    expect(scope.detail).toMatch(/verifying/);
  });

  it('budget check fails at 0 or below', () => {
    expect(computeGateChecks({ ...base, budgetUsd: 0 }).find((i) => i.id === 'budget')!.passed).toBe(false);
    expect(computeGateChecks({ ...base, budgetUsd: -1 }).find((i) => i.id === 'budget')!.passed).toBe(false);
  });

  it('allowlist check fails when empty or blank-only', () => {
    expect(computeGateChecks({ ...base, toolAllowlist: [] }).find((i) => i.id === 'allowlist')!.passed).toBe(false);
    expect(computeGateChecks({ ...base, toolAllowlist: ['  '] }).find((i) => i.id === 'allowlist')!.passed).toBe(false);
  });

  it('allGateChecksPass is false if any single check fails', () => {
    const items = computeGateChecks({ ...base, budgetUsd: 0 });
    expect(allGateChecksPass(items)).toBe(false);
  });
});
