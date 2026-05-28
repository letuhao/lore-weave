#!/usr/bin/env node
// Bundle-size guard for V0 AC-FG-15: gzipped JS+CSS ≤ 700 KB.
// Runs after `vite build`. Reads dist/assets/*.js + dist/assets/*.css,
// computes gzip sizes, compares against budget. Exit non-zero on regression.
//
// Run: `node scripts/check-bundle-size.mjs` (from frontend-game/)
// Override budget: `LOREWEAVE_BUNDLE_BUDGET_KB=800 node scripts/...`

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { join } from 'node:path';

const BUDGET_KB = Number(process.env.LOREWEAVE_BUNDLE_BUDGET_KB ?? 700);
const DIST = './dist/assets';

let dist;
try {
  dist = readdirSync(DIST);
} catch {
  console.error(`dist/assets/ not found — run \`pnpm build\` first`);
  process.exit(2);
}

let totalRaw = 0;
let totalGz = 0;
const lines = [];

for (const file of dist) {
  if (!/\.(js|css)$/.test(file)) continue;
  if (file.endsWith('.map')) continue;
  const path = join(DIST, file);
  const raw = readFileSync(path);
  const gz = gzipSync(raw, { level: 9 });
  totalRaw += raw.length;
  totalGz += gz.length;
  lines.push(`  ${file}: ${(raw.length / 1024).toFixed(2)} KB raw / ${(gz.length / 1024).toFixed(2)} KB gzip`);
}

const totalKb = totalGz / 1024;
const ok = totalKb <= BUDGET_KB;

console.log('Bundle size report (V0 AC-FG-15):');
lines.forEach((l) => console.log(l));
console.log(`  ────────`);
console.log(`  TOTAL: ${(totalRaw / 1024).toFixed(2)} KB raw / ${totalKb.toFixed(2)} KB gzip`);
console.log(`  Budget: ${BUDGET_KB} KB gzip`);

if (!ok) {
  console.error(`\n❌ FAIL — bundle exceeds budget by ${(totalKb - BUDGET_KB).toFixed(2)} KB`);
  console.error('Consider: code splitting (dynamic import), manualChunks in vite.config.ts, or raising the budget if intentional.');
  process.exit(1);
}

console.log(`\n✅ OK — ${(BUDGET_KB - totalKb).toFixed(2)} KB headroom`);
