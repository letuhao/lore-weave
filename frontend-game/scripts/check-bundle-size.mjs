#!/usr/bin/env node
// Bundle-size guard for V0 AC-FG-15: gzipped **initial-load** JS+CSS ≤ 700 KB.
// Runs after `vite build`.
//
// What counts: AC-FG-15 is a *load-performance* budget, so it measures the
// EAGER initial bundle — exactly the assets `dist/index.html` references (the
// entry script + its `modulepreload` static-import graph + stylesheets).
// **Route-level lazy chunks** (e.g. the 3D world-preview viewer's three.js,
// `import()`-split so it loads only when that route opens) are NOT in
// index.html, so they don't count against the first-paint budget — they're
// reported separately for visibility. (Before code-splitting existed this script
// summed every chunk; that over-counted code a user may never load.)
//
// Run: `node scripts/check-bundle-size.mjs` (from frontend-game/)
// Override budget: `LOREWEAVE_BUNDLE_BUDGET_KB=800 node scripts/...`

import { readdirSync, readFileSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { basename, join } from 'node:path';

const BUDGET_KB = Number(process.env.LOREWEAVE_BUNDLE_BUDGET_KB ?? 700);
const DIST = './dist';
const ASSETS = join(DIST, 'assets');

let html;
try {
  html = readFileSync(join(DIST, 'index.html'), 'utf8');
} catch {
  console.error(`dist/index.html not found — run \`pnpm build\` first`);
  process.exit(2);
}

let assetFiles;
try {
  assetFiles = readdirSync(ASSETS).filter((f) => /\.(js|css)$/.test(f) && !f.endsWith('.map'));
} catch {
  console.error(`dist/assets/ not found — run \`pnpm build\` first`);
  process.exit(2);
}

// The eager initial-load set = every JS/CSS asset referenced by index.html
// (entry `src=`, `modulepreload`/stylesheet `href=`). Matched by basename so a
// non-default base path doesn't matter.
const referenced = new Set();
for (const m of html.matchAll(/(?:src|href)="([^"]+\.(?:js|css))"/g)) {
  referenced.add(basename(m[1]));
}

const gz = (file) => gzipSync(readFileSync(join(ASSETS, file)), { level: 9 }).length;

let initialGz = 0;
let lazyGz = 0;
const initialLines = [];
const lazyLines = [];
for (const file of assetFiles) {
  const size = gz(file);
  const line = `  ${file}: ${(size / 1024).toFixed(2)} KB gzip`;
  if (referenced.has(file)) {
    initialGz += size;
    initialLines.push(line);
  } else {
    lazyGz += size;
    lazyLines.push(line);
  }
}

// Fail-loud if no eager asset was identified — otherwise a Vite output change
// that breaks the index.html parse would make `initialGz = 0 ≤ budget` a silent
// false-green, turning the CI budget into a no-op nobody notices.
if (initialLines.length === 0) {
  console.error(
    'No eager JS/CSS asset found via dist/index.html — cannot measure the initial ' +
      'bundle (did the Vite output format change?). Refusing to report a false pass.',
  );
  process.exit(2);
}

const initialKb = initialGz / 1024;
const ok = initialKb <= BUDGET_KB;

console.log('Bundle size report (AC-FG-15 — initial load):');
initialLines.forEach((l) => console.log(l));
console.log(`  ────────`);
console.log(`  INITIAL (eager): ${initialKb.toFixed(2)} KB gzip`);
console.log(`  Budget: ${BUDGET_KB} KB gzip`);
if (lazyLines.length > 0) {
  console.log(`\n  Lazy route chunks (excluded from the budget — loaded on demand):`);
  lazyLines.forEach((l) => console.log(l));
  console.log(`  lazy total: ${(lazyGz / 1024).toFixed(2)} KB gzip`);
}

if (!ok) {
  console.error(`\n❌ FAIL — initial bundle exceeds budget by ${(initialKb - BUDGET_KB).toFixed(2)} KB`);
  console.error('Consider: lazy-load a heavy route (dynamic import), manualChunks in vite.config.ts, or raise the budget if intentional.');
  process.exit(1);
}

console.log(`\n✅ OK — ${(BUDGET_KB - initialKb).toFixed(2)} KB headroom`);
