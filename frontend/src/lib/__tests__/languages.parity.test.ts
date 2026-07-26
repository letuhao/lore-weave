// D-4/D13 — the frontend LANGUAGE_REGISTRY must stay in exact parity with the content-language
// SSOT (contracts/languages.contract.json). Adding/removing/reordering a language in one place
// without the other reds this test. The Python mirror (translation-service) has the twin test.
import { describe, it, expect } from 'vitest';
import { LANGUAGE_REGISTRY } from '../languages';
import contract from '../../../../contracts/languages.contract.json';

describe('LANGUAGE_REGISTRY ↔ languages.contract.json parity', () => {
  it('matches the SSOT exactly (order, codes, flags, all fields)', () => {
    const fromRegistry = LANGUAGE_REGISTRY.map((l) => ({
      code: l.code,
      englishName: l.englishName,
      endonym: l.endonym,
      script: l.script,
      dir: l.dir,
      uiLocale: l.uiLocale,
      translationTarget: l.translationTarget,
    }));
    expect(fromRegistry).toEqual(contract.languages);
  });

  it('every code is unique', () => {
    const codes = contract.languages.map((l) => l.code);
    expect(new Set(codes).size).toBe(codes.length);
  });
});
