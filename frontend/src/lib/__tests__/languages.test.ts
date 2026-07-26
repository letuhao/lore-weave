import { describe, it, expect } from 'vitest';
import {
  getLanguageName,
  getLanguageDir,
  LANGUAGE_NAMES,
  LANGUAGE_REGISTRY,
  LANGUAGE_BY_CODE,
  UI_LOCALES,
  TRANSLATION_TARGETS,
} from '../languages';

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

  it('is derived from the registry (no drift)', () => {
    for (const l of LANGUAGE_REGISTRY) {
      expect(LANGUAGE_NAMES[l.code]).toBe(l.endonym);
    }
  });
});

describe('LANGUAGE_REGISTRY', () => {
  it('ships the full 18-locale UI set (4 strategic tiers)', () => {
    for (const code of ['en', 'vi', 'ja', 'ko', 'zh-CN', 'zh-TW', 'es', 'pt-BR', 'fr', 'de', 'ru', 'id', 'ms', 'tr', 'ar', 'hi', 'bn', 'th']) {
      expect(LANGUAGE_BY_CODE[code], `missing ${code}`).toBeDefined();
      expect(LANGUAGE_BY_CODE[code].uiLocale).toBe(true);
    }
    expect(UI_LOCALES).toHaveLength(18);
  });

  it('has unique codes and non-empty endonyms', () => {
    const codes = LANGUAGE_REGISTRY.map((l) => l.code);
    expect(new Set(codes).size).toBe(codes.length);
    for (const l of LANGUAGE_REGISTRY) expect(l.endonym.length).toBeGreaterThan(0);
  });

  it('distinguishes Simplified vs Traditional Chinese as separate locales', () => {
    expect(LANGUAGE_BY_CODE['zh-CN'].endonym).toBe('简体中文');
    expect(LANGUAGE_BY_CODE['zh-TW'].endonym).toBe('繁體中文');
    expect(LANGUAGE_BY_CODE['zh-CN'].script).toBe('Hans');
    expect(LANGUAGE_BY_CODE['zh-TW'].script).toBe('Hant');
  });
});

describe('getLanguageDir', () => {
  it('marks Arabic RTL and everything else LTR', () => {
    expect(getLanguageDir('ar')).toBe('rtl');
    expect(getLanguageDir('en')).toBe('ltr');
    expect(getLanguageDir('he')).toBe('ltr'); // not in registry yet → safe LTR default
  });

  it('falls back to the base subtag for regional codes', () => {
    expect(getLanguageDir('ar-EG')).toBe('rtl');
    expect(getLanguageDir('en-US')).toBe('ltr');
  });

  it('defaults unknown codes to LTR', () => {
    expect(getLanguageDir('xx')).toBe('ltr');
  });
});

describe('TRANSLATION_TARGETS', () => {
  it('surfaces the registry targets in order', () => {
    expect(TRANSLATION_TARGETS.length).toBeGreaterThanOrEqual(15);
    expect(TRANSLATION_TARGETS.every((l) => l.translationTarget)).toBe(true);
  });
});
