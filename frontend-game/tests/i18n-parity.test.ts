// Locale parity — the guard that keeps translation debt from accumulating.
//
// The failure this prevents is not exotic, it is the DEFAULT outcome: someone
// adds `combat.json` for English, ships, and three locales silently fall back
// to English forever. i18next's `fallbackLng` makes that invisible at runtime —
// nothing throws, nothing logs, the UI just quietly speaks the wrong language.
// So the only place it can be caught is here.
//
// English is the reference because it is `DEFAULT_LOCALE` / `fallbackLng`. Any
// key present in en MUST exist in every other locale, and vice versa (a key in
// vi but not en is dead weight — nothing will ever look it up through the
// fallback chain).

import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { GAME_LOCALES, DEFAULT_LOCALE } from '@loreweave/i18n';

const LOCALES_DIR = path.resolve(__dirname, '../../packages/i18n/locales');

function namespacesOf(locale: string): string[] {
  return readdirSync(path.join(LOCALES_DIR, locale))
    .filter((f) => f.endsWith('.json') && !f.startsWith('_'))
    .map((f) => f.replace(/\.json$/, ''))
    .sort();
}

function load(locale: string, ns: string): Record<string, unknown> {
  return JSON.parse(readFileSync(path.join(LOCALES_DIR, locale, `${ns}.json`), 'utf8')) as Record<
    string,
    unknown
  >;
}

/** Dotted leaf paths, so a nested `error.network` is compared as one key. */
function leafKeys(obj: unknown, prefix = ''): string[] {
  if (obj === null || typeof obj !== 'object' || Array.isArray(obj)) return [prefix];
  return Object.entries(obj as Record<string, unknown>)
    .flatMap(([k, v]) => leafKeys(v, prefix ? `${prefix}.${k}` : k))
    .sort();
}

const reference = DEFAULT_LOCALE;
const otherLocales = GAME_LOCALES.filter((l) => l !== reference);

describe('i18n locale parity', () => {
  it('ships more than one locale and a real reference (guards a vacuous suite)', () => {
    // Without this, deleting every locale but `en` would turn the whole file
    // green — zero comparisons, reported as "parity holds".
    expect(GAME_LOCALES.length).toBeGreaterThan(1);
    expect(otherLocales.length).toBeGreaterThan(0);
    expect(namespacesOf(reference).length).toBeGreaterThan(0);
  });

  it('every locale directory exists and carries the same namespaces', () => {
    const expected = namespacesOf(reference);
    for (const locale of otherLocales) {
      expect(namespacesOf(locale), `namespaces of ${locale}`).toEqual(expected);
    }
  });

  it.each(namespacesOf(reference))('namespace "%s" has identical keys in every locale', (ns) => {
    const expected = leafKeys(load(reference, ns));
    expect(expected.length).toBeGreaterThan(0);
    for (const locale of otherLocales) {
      expect(leafKeys(load(locale, ns)), `${locale}/${ns}.json`).toEqual(expected);
    }
  });

  it.each(GAME_LOCALES)('locale "%s" has no empty strings', (locale) => {
    for (const ns of namespacesOf(locale)) {
      const flat = (function walk(o: unknown, p = ''): [string, unknown][] {
        if (o === null || typeof o !== 'object') return [[p, o]];
        return Object.entries(o as Record<string, unknown>).flatMap(([k, v]) =>
          walk(v, p ? `${p}.${k}` : k),
        );
      })(load(locale, ns));

      for (const [key, value] of flat) {
        // An empty string is WORSE than a missing key: i18next treats it as a
        // valid translation, so the fallback never fires and the UI renders
        // blank. A missing key at least falls back to English.
        expect(typeof value, `${locale}/${ns}: ${key}`).toBe('string');
        expect(String(value).trim(), `${locale}/${ns}: ${key} is empty`).not.toBe('');
      }
    }
  });
});
