import { describe, it, expect } from 'vitest';
import en from '../locales/en/campaigns.json';
import vi from '../locales/vi/campaigns.json';
import ja from '../locales/ja/campaigns.json';
import zhTW from '../locales/zh-TW/campaigns.json';

// D-S5C-I18N — guard the campaigns namespace: every locale must carry exactly the
// same keys as the English SSOT (no missing/extra → no silent English fallback), and
// each value must preserve the same {{interpolation}} placeholders (a dropped {{error}}
// or {{count}} renders a broken string at runtime).

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

const placeholders = (s: string): string[] =>
  (s.match(/\{\{\s*[a-zA-Z0-9_]+\s*\}\}/g) ?? []).map((p) => p.replace(/\s/g, '')).sort();

describe('campaigns i18n parity (D-S5C-I18N)', () => {
  const enKeys = Object.keys(enFlat).sort();

  for (const [lng, flat] of Object.entries(locales)) {
    it(`${lng} has exactly the English key set`, () => {
      expect(Object.keys(flat).sort()).toEqual(enKeys);
    });

    it(`${lng} preserves every {{placeholder}}`, () => {
      for (const key of enKeys) {
        expect(placeholders(flat[key]), `${lng}:${key}`).toEqual(placeholders(enFlat[key]));
      }
    });

    it(`${lng} has no empty translations`, () => {
      for (const key of enKeys) expect(flat[key].trim(), `${lng}:${key}`).not.toBe('');
    });
  }
});
