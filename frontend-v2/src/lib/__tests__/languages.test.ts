import { describe, it, expect } from 'vitest';
import { getLanguageName, LANGUAGE_NAMES } from '../languages';

describe('getLanguageName', () => {
  it('returns native name for known codes', () => {
    expect(getLanguageName('ja')).toBe('日本語');
    expect(getLanguageName('en')).toBe('English');
    expect(getLanguageName('vi')).toBe('Tiếng Việt');
    expect(getLanguageName('zh-TW')).toBe('繁體中文');
  });

  it('returns the code itself for unknown languages', () => {
    expect(getLanguageName('xx')).toBe('xx');
    expect(getLanguageName('unknown')).toBe('unknown');
  });

  it('is case-sensitive', () => {
    expect(getLanguageName('EN')).toBe('EN');
    expect(getLanguageName('JA')).toBe('JA');
  });
});

describe('LANGUAGE_NAMES', () => {
  it('contains expected language entries', () => {
    expect(Object.keys(LANGUAGE_NAMES).length).toBeGreaterThanOrEqual(13);
    expect(LANGUAGE_NAMES).toHaveProperty('ko', '한국어');
    expect(LANGUAGE_NAMES).toHaveProperty('fr', 'Français');
  });
});
