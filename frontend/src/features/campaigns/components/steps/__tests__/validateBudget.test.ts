import { describe, it, expect } from 'vitest';
import { validateBudget } from '../ReviewStep';

describe('validateBudget (D-S5C-BUDGET-VALIDATE)', () => {
  it('treats blank/whitespace as uncapped (valid)', () => {
    expect(validateBudget('')).toBeNull();
    expect(validateBudget('   ')).toBeNull();
  });

  it('accepts a positive amount below the ceiling', () => {
    expect(validateBudget('5')).toBeNull();
    expect(validateBudget('0.0001')).toBeNull();
    expect(validateBudget('99999999')).toBeNull();
  });

  it('rejects non-numbers, zero, and negatives as invalid', () => {
    expect(validateBudget('abc')).toBe('invalid');
    expect(validateBudget('0')).toBe('invalid');
    expect(validateBudget('-3')).toBe('invalid');
  });

  it('rejects amounts at/above the NUMERIC(16,8) ceiling', () => {
    expect(validateBudget('100000000')).toBe('tooLarge');
    expect(validateBudget('250000000')).toBe('tooLarge');
  });
});
