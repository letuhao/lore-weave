import { describe, it, expect } from 'vitest';
import en from '../locales/en/onboarding.json';
import vi from '../locales/vi/onboarding.json';
import ja from '../locales/ja/onboarding.json';
import zhTW from '../locales/zh-TW/onboarding.json';

// C22 — guard the onboarding namespace: every locale carries exactly the English
// key set (no silent English fallback on a missing intent label) and no empties.

type Json = Record<string, unknown>;

function flatten(obj: Json, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object') Object.assign(out, flatten(v as Json, key));
    else out[key] = String(v);
  }
  return out;
}

const enFlat = flatten(en as Json);
const locales: Record<string, Record<string, string>> = {
  vi: flatten(vi as Json),
  ja: flatten(ja as Json),
  'zh-TW': flatten(zhTW as Json),
};

describe('onboarding i18n parity (C22)', () => {
  const enKeys = Object.keys(enFlat).sort();

  it('English carries the four intent labels + headings', () => {
    expect(enKeys).toContain('heading');
    for (const id of ['write', 'world', 'translate', 'explore']) {
      expect(enKeys).toContain(`intent.${id}.title`);
      expect(enKeys).toContain(`intent.${id}.desc`);
    }
  });

  for (const [lng, flat] of Object.entries(locales)) {
    it(`${lng} has exactly the English key set`, () => {
      expect(Object.keys(flat).sort()).toEqual(enKeys);
    });

    it(`${lng} has no empty translations`, () => {
      for (const key of enKeys) expect(flat[key].trim(), `${lng}:${key}`).not.toBe('');
    });
  }
});
