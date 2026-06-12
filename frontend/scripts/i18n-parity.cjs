#!/usr/bin/env node
/**
 * i18n key-parity guard.
 *
 * Asserts that every locale (vi/ja/zh-TW) carries exactly the same namespace
 * files and key set as the reference locale `en`. Catches the class of bug
 * that produced the mixed-language UI (e.g. `books.json` existing only for en).
 *
 * Usage:  node scripts/i18n-parity.cjs
 * Exit:   0 = parity holds, 1 = drift found (prints the offending keys).
 */
const fs = require('fs');
const path = require('path');

const LOCALES_DIR = path.join(__dirname, '..', 'src', 'i18n', 'locales');
const REF = 'en';

function flatten(obj, prefix = '') {
  const keys = [];
  for (const k of Object.keys(obj)) {
    const v = obj[k];
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) keys.push(...flatten(v, key));
    else keys.push(key);
  }
  return keys;
}

function load(locale, ns) {
  return JSON.parse(fs.readFileSync(path.join(LOCALES_DIR, locale, `${ns}.json`), 'utf8'));
}

const locales = fs.readdirSync(LOCALES_DIR).filter((d) =>
  fs.statSync(path.join(LOCALES_DIR, d)).isDirectory(),
);
const targets = locales.filter((l) => l !== REF);
const refNamespaces = fs
  .readdirSync(path.join(LOCALES_DIR, REF))
  .filter((f) => f.endsWith('.json'))
  .map((f) => f.replace('.json', ''));

let problems = 0;
for (const ns of refNamespaces) {
  const refKeys = new Set(flatten(load(REF, ns)));
  for (const loc of targets) {
    const file = path.join(LOCALES_DIR, loc, `${ns}.json`);
    if (!fs.existsSync(file)) {
      console.error(`✗ ${loc}/${ns}.json — FILE MISSING (${refKeys.size} keys in en)`);
      problems++;
      continue;
    }
    const locKeys = new Set(flatten(load(loc, ns)));
    const missing = [...refKeys].filter((k) => !locKeys.has(k));
    const extra = [...locKeys].filter((k) => !refKeys.has(k));
    if (missing.length) {
      console.error(`✗ ${loc}/${ns}.json — missing ${missing.length}: ${missing.join(', ')}`);
      problems++;
    }
    if (extra.length) {
      console.error(`✗ ${loc}/${ns}.json — extra ${extra.length} (not in en): ${extra.join(', ')}`);
      problems++;
    }
  }
}

if (problems) {
  console.error(`\ni18n parity FAILED: ${problems} namespace/locale problem(s).`);
  process.exit(1);
}
console.log(`i18n parity OK — ${refNamespaces.length} namespaces × ${targets.length} locales aligned to ${REF}.`);
