import { describe, it, expect } from 'vitest';
import enComposition from '../locales/en/composition.json';
import viComposition from '../locales/vi/composition.json';
import jaComposition from '../locales/ja/composition.json';
import zhTWComposition from '../locales/zh-TW/composition.json';
import enWorld from '../locales/en/world.json';
import viWorld from '../locales/vi/world.json';
import jaWorld from '../locales/ja/world.json';
import zhTWWorld from '../locales/zh-TW/world.json';

// Review item #4 — guard the composition + world namespaces (onboarding/campaigns
// already have parity tests; these two had none). Every locale must carry exactly
// the same flattened key set as the English SSOT (no missing/extra → no silent
// English fallback), preserve every {{interpolation}} placeholder, and have no empties.

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

const placeholders = (s: string): string[] =>
  (s.match(/\{\{\s*[a-zA-Z0-9_]+\s*\}\}/g) ?? []).map((p) => p.replace(/\s/g, '')).sort();

function runParity(
  namespace: string,
  en: Json,
  others: Record<string, Json>,
): void {
  const enFlat = flatten(en);
  const enKeys = Object.keys(enFlat).sort();
  const locales: Record<string, Record<string, string>> = Object.fromEntries(
    Object.entries(others).map(([lng, json]) => [lng, flatten(json)]),
  );

  describe(`${namespace} i18n parity (review #4)`, () => {
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
}

runParity('composition', enComposition as Json, {
  vi: viComposition as Json,
  ja: jaComposition as Json,
  'zh-TW': zhTWComposition as Json,
});

runParity('world', enWorld as Json, {
  vi: viWorld as Json,
  ja: jaWorld as Json,
  'zh-TW': zhTWWorld as Json,
});
