// One-shot probe — POSTs the demo template to tilemap-service /render
// and reports distinct TerrainKind count + per-kind histogram in
// terrain_layer. Used during chunk-C verification to set the AC-BIOME-8
// threshold correctly + as the operator-runnable smoke for DEFERRED #041
// (CI gate).
//
// Usage:
//   node scripts/check_biome_variety.js                  # default seed 1
//   node scripts/check_biome_variety.js 42               # single seed
//   node scripts/check_biome_variety.js sweep 1 100      # multi-seed sweep
//
// LOW-4 fix from chunk-C /review-impl: when the backend returns 401,
// emit an actionable hint pointing at LOREWEAVE_INTERNAL_TOKEN rather
// than dumping the raw error body.
//
// LOW-5 fix from chunk-C /review-impl: `sweep` mode runs 1..N seeds and
// reports min/max/mean distinct-terrains so threshold calibration has
// breadth, not just 3 hand-picked seeds.

const fs = require('fs');
const path = require('path');

const TEMPLATE_PATH = path.join(
  __dirname,
  '..',
  'frontend-game',
  'public',
  'templates',
  'minimal.json',
);
const TOKEN = process.env.LOREWEAVE_INTERNAL_TOKEN ?? 'dev_internal_token';
const URL = 'http://localhost:8220/internal/v1/tilemaps/render';

async function renderOnce(template, seed) {
  const body = {
    channel_id: `ch_probe_${seed}`,
    tier: 'town',
    grid_size: { width: 48, height: 48 },
    seed,
    template,
  };
  const res = await fetch(URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${TOKEN}`,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    if (res.status === 401) {
      throw new Error(
        `render returned 401 Unauthorized. Set LOREWEAVE_INTERNAL_TOKEN ` +
          `env var to the token the backend was started with (the dev ` +
          `default is "dev_internal_token"). Server body: ${text}`,
      );
    }
    throw new Error(`render failed: ${res.status} ${res.statusText}\n${text}`);
  }
  return res.json();
}

function summarize(view) {
  const layer = view.terrain_layer;
  const distinct = new Set(layer.filter((v) => v !== 0));
  const histogram = {};
  for (const v of layer) histogram[v] = (histogram[v] ?? 0) + 1;
  return {
    distinct: distinct.size,
    tiles: layer.length,
    histogram,
    decorations: view.object_placements.length,
  };
}

async function single(template, seed) {
  const view = await renderOnce(template, seed);
  const s = summarize(view);
  console.log(`seed=${seed}  distinct terrains=${s.distinct}  tiles=${s.tiles}`);
  console.log(`histogram: ${JSON.stringify(s.histogram)}`);
  console.log(`decorations: ${s.decorations}`);
}

async function sweep(template, from, to) {
  let min = Infinity;
  let max = -Infinity;
  let total = 0;
  const distinctCounts = [];
  for (let s = from; s <= to; s++) {
    const view = await renderOnce(template, s);
    const sum = summarize(view);
    distinctCounts.push(sum.distinct);
    min = Math.min(min, sum.distinct);
    max = Math.max(max, sum.distinct);
    total += sum.distinct;
  }
  const n = to - from + 1;
  const mean = total / n;
  console.log(`sweep seeds ${from}..${to} (n=${n})`);
  console.log(`  distinct terrains: min=${min}  max=${max}  mean=${mean.toFixed(2)}`);
  console.log(`  per-seed counts: ${distinctCounts.join(', ')}`);
  console.log();
  console.log(`AC-BIOME-8 threshold recommendation: floor(min) - 0 = ${min} (use ≥ ${min})`);
}

async function main() {
  const template = JSON.parse(fs.readFileSync(TEMPLATE_PATH, 'utf8'));
  if (process.argv[2] === 'sweep') {
    const from = Number(process.argv[3] ?? 1);
    const to = Number(process.argv[4] ?? 100);
    await sweep(template, from, to);
  } else {
    const seed = Number(process.argv[2] ?? 1);
    await single(template, seed);
  }
}

main().catch((err) => {
  console.error(err.message ?? err);
  process.exit(1);
});
