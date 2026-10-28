import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { existsSync } from 'node:fs';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../../', import.meta.url));
const serverEntry = join(root, 'services/game-server/dist/index.js');
const driverEntry = fileURLToPath(new URL('./ws_echo.mjs', import.meta.url));

async function runDriver(env) {
  const child = spawn(process.execPath, [driverEntry], { cwd: root, env });
  let output = '';
  child.stdout.on('data', (data) => { output += data; });
  child.stderr.on('data', (data) => { output += data; });
  const timer = setTimeout(() => child.kill('SIGKILL'), 10000);
  try {
    const [code] = await once(child, 'close');
    return { code, output };
  } finally {
    clearTimeout(timer);
  }
}

test('F4 SDK joins the real 0.17 server, echoes, and rejects bad auth', { timeout: 20000 }, async () => {
  // NV-6: colyseus.js 0.16 failed the real handshake before the SDK migration
  // (undefined matchmake response, driver exit 3); HTTP-only success hid it.
  assert.ok(existsSync(serverEntry), 'build services/game-server before running test:live');
  const reservation = createServer();
  reservation.listen(0, '127.0.0.1');
  await once(reservation, 'listening');
  const port = reservation.address().port;
  await new Promise((resolve) => reservation.close(resolve));

  const dir = await mkdtemp(join(tmpdir(), 'f4-sdk-test-'));
  const env = { ...process.env, PORT: String(port), LW_WS_ALLOW_DEV_AUTH: '1',
    LOREWEAVE_INTERNAL_TOKEN: 'f4-test-token', LW_WS_MSG_PER_WINDOW: '10000',
    TARGET_WS: `ws://127.0.0.1:${port}`, WS_ROUNDTRIPS: '10' };
  // Only this ephemeral process uses static auth; never connect it to live Redis.
  delete env.LW_WS_REDIS_URL;
  const server = spawn(process.execPath, [serverEntry], { cwd: root, env });
  let serverLog = '';
  server.stdout.on('data', (data) => { serverLog += data; });
  server.stderr.on('data', (data) => { serverLog += data; });
  try {
    let ready = false;
    for (let i = 0; i < 60; i++) {
      try {
        ready = (await fetch(`http://127.0.0.1:${port}/livez`)).ok;
        if (ready) break;
      } catch { /* Listener has not started yet. */ }
      assert.equal(server.exitCode, null, serverLog);
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    assert.ok(ready, serverLog);
    const summaryPath = join(dir, 'summary.json');
    const clean = await runDriver({ ...env, SUMMARY_OUT: summaryPath });
    assert.equal(clean.code, 0, clean.output);
    const summary = JSON.parse(await readFile(summaryPath, 'utf8'));
    assert.equal(summary.metric, 'ws_echo_roundtrip');
    assert.equal(summary.model, 'closed-loop (@colyseus/sdk client)');
    assert.equal(summary.count, 10);
    assert.ok(summary.max > 0 && Number.isFinite(summary.p99));

    const rejectedPath = join(dir, 'rejected.json');
    const rejected = await runDriver({ ...env, LOREWEAVE_INTERNAL_TOKEN: 'wrong-token',
      SUMMARY_OUT: rejectedPath });
    assert.equal(rejected.code, 3, rejected.output);
    assert.ok(!existsSync(rejectedPath), 'rejected auth must not report a latency artifact');
  } finally {
    if (server.exitCode === null && server.signalCode === null) {
      const closed = once(server, 'close');
      server.kill('SIGTERM');
      const timer = setTimeout(() => server.kill('SIGKILL'), 3000);
      try { await closed; } finally { clearTimeout(timer); }
    }
    await rm(dir, { recursive: true, force: true });
  }
});
