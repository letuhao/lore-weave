import { describe, it, expect } from 'vitest';
import en from '../locales/en/chat.json';
import vi from '../locales/vi/chat.json';
import ja from '../locales/ja/chat.json';
import zhTW from '../locales/zh-TW/chat.json';

// Guard the chat namespace (added with RAID Wave C4 @-mention strings): every locale
// must carry exactly the same keys as the English SSOT (no missing/extra → no silent
// English fallback), and each value must preserve the same {{interpolation}}
// placeholders (a dropped {{count}} renders a broken string at runtime).

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

describe('chat i18n parity', () => {
  const enKeys = Object.keys(enFlat).sort();

  for (const [lng, flat] of Object.entries(locales)) {
    it(`${lng} has exactly the English key set`, () => {
      expect(Object.keys(flat).sort()).toEqual(enKeys);
    });

    it(`${lng} preserves interpolation placeholders`, () => {
      for (const key of enKeys) {
        if (!(key in flat)) continue; // covered by the key-set assertion
        expect(placeholders(flat[key]), `${lng}:${key}`).toEqual(placeholders(enFlat[key]));
      }
    });
  }
});
