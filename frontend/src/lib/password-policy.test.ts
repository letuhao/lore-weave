import { describe, expect, it } from 'vitest';
import { passwordMeetsPolicy } from './password-policy';

describe('passwordMeetsPolicy', () => {
  it('accepts an eight-plus byte password with a letter and digit', () => {
    expect(passwordMeetsPolicy('GameTest2026')).toBe(true);
  });

  it('rejects digits-only passwords instead of sending them to auth-service', () => {
    expect(passwordMeetsPolicy('12345678')).toBe(false);
  });

  it('rejects passwords without a digit', () => {
    expect(passwordMeetsPolicy('abcdefgh')).toBe(false);
  });

  it('accepts Unicode letters and digits like auth-service', () => {
    expect(passwordMeetsPolicy('日本語パス1234')).toBe(true);
  });
});
