// TMP-Q1 chunk D — manual smoke gate for AC-DECO-8.
// Renders the demo template via /internal/v1/tilemaps/render and asserts
// total decorations >= 20.
//
// Prereq: tilemap-service running on http://127.0.0.1:8220
//   LOREWEAVE_INTERNAL_TOKEN=<token> \
//   TILEMAP_HTTP_BIND=0.0.0.0:8220 \
//   target/release/tilemap-service.exe serve
//
// Usage:
//   node scripts/smoke_decoration_count.js [seed]
//   LOREWEAVE_INTERNAL_TOKEN=<token> node scripts/smoke_decoration_count.js
//
// Per-zone bucketing was DROPPED (chunk-D /review-impl MED-1): vanilla
// JSON.parse loses u64 precision on TileMask.bits high-bit words, so
// per-zone reports could silently misattribute placements. The total
// count from view.object_placements.length is precision-safe (no
// BigInt arithmetic needed). The frontend's parseTilemapView handles
// u64 correctly via regex-quote + BigInt; this script doesn't replicate
// that complexity for a gate-only tool.

const fs = require('fs');
const http = require('http');
const path = require('path');

const seed = parseInt(process.argv[2] ?? '1', 10);
const token = process.env.LOREWEAVE_INTERNAL_TOKEN ?? 'dev_internal_token';
const templatePath = path.join(__dirname, '..', 'frontend-game', 'public', 'templates', 'minimal.json');
const template = JSON.parse(fs.readFileSync(templatePath, 'utf-8'));

const body = JSON.stringify({
  template,
  channel_id: 'ch_v1_viewer',
  tier: 'town',
  grid_size: { width: 64, height: 64 },
  seed,
});

const req = http.request(
  {
    host: '127.0.0.1',
    port: 8220,
    path: '/internal/v1/tilemaps/render',
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      'Content-Length': Buffer.byteLength(body),
    },
  },
  (res) => {
    let chunks = [];
    res.on('data', (c) => chunks.push(c));
    res.on('end', () => {
      const text = Buffer.concat(chunks).toString();
      if (res.statusCode === 401) {
        console.error('401 Unauthorized.');
        console.error('Hint: backend token differs from the one this script sent.');
        console.error('  Set LOREWEAVE_INTERNAL_TOKEN=<your-token> and re-run.');
        process.exit(1);
      }
      if (res.statusCode !== 200) {
        console.error(`HTTP ${res.statusCode}: ${text.slice(0, 500)}`);
        process.exit(1);
      }
      // Vanilla JSON.parse is safe here — we only inspect object_placements
      // (no TileMask.bits access). See MED-1 doc-comment above.
      const v = JSON.parse(text);
      const decoFilter = (p) => p.primitive === 'decoration' || p.kind === 'decoration';
      const total = v.object_placements.length;
      const deco = v.object_placements.filter(decoFilter).length;
      console.log(`seed=${seed} tier=town grid=64x64`);
      console.log(`zones: ${v.zones.length} (${v.zones.map((z) => `${z.zone_id}/${z.terrain_type}`).join(', ')})`);
      console.log(`total placements: ${total}`);
      console.log(`decorations: ${deco}`);
      if (deco < 20) {
        console.error(`FAIL: AC-DECO-8 requires ≥ 20 decorations, got ${deco}`);
        process.exit(1);
      }
      console.log(`PASS: AC-DECO-8 (≥ 20)`);
    });
  },
);
req.on('error', (e) => {
  console.error(`request error: ${e.message}`);
  console.error('Hint: is tilemap-service running on :8220?');
  process.exit(1);
});
req.write(body);
req.end();
