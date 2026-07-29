import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// Vite config for frontend-game.
//
// PORT 5176 — NOT 5174. The original "5174 per spec AC-FG-3 (frontend/ owns
// 5173)" went stale: `frontend/` moved to 5174, and with `strictPort: true`
// running both dev servers hard-failed. infra/docker-compose.yml already
// resolved this on 2026-07-17 (host 5176 → container 5174) and the canonical
// split is 5174 = frontend · 5175 = cms-frontend · 5176 = frontend-game — but
// the fix never reached THIS file, so the compose path and the `pnpm dev` path
// disagreed.
//
// The port is also this app's browser ORIGIN, and tilemap-service /
// roleplay-service / game-server all default `LOREWEAVE_CORS_ORIGINS` to
// http://localhost:5176. Serving dev on 5174 therefore got CORS-blocked by
// every backend it talks to. Move this port and those three defaults must move
// with it.
//
// HMR rule for src/game/** (spec AC-FG-14): when a Phaser scene file
// changes, do a controlled full-page-reload instead of letting HMR try
// to hot-swap Phaser internals (which freezes the canvas silently).
// React component edits keep normal HMR.

// BASE PATH. Standalone the app is served at '/', but under the MED-8
// single-domain topology it lives at '/game/' behind the public entry point —
// and that is not cosmetic: ONE ORIGIN is what makes localStorage shared, which
// is what makes the session (`lw_auth`) and the language (`lw_language`) carry
// over from the novel app. Two origins = two sessions, no matter how correct
// the client code is.
//
// Vite exposes this as `import.meta.env.BASE_URL`, which App.tsx feeds to the
// router's basename so both modes route correctly with no second switch.
const basePath = process.env.VITE_BASE_PATH ?? '/';

export default defineConfig({
  base: basePath,
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@game': path.resolve(__dirname, './src/game'),
    },
  },
  server: {
    port: 5176,
    strictPort: true,
    host: 'localhost',
    // `/v1` must be SAME-ORIGIN, not an absolute cross-origin URL. With the
    // HttpOnly-cookie decision this stops being a convenience and becomes
    // load-bearing: a cookie scoped to the gateway host is simply not sent to
    // a page served from localhost:5176, so a cross-origin login cannot work
    // at all. Proxying keeps the browser on one origin, which is also what
    // makes the session shared with `frontend/` (MED-8 single-domain).
    proxy: {
      '/v1': {
        target: process.env.VITE_GATEWAY_URL ?? 'http://localhost:3123',
        changeOrigin: false, // preserve Origin — the WS ticket endpoint binds to it
      },
    },
  },
  preview: {
    port: 5176,
    strictPort: true,
  },
  build: {
    target: 'es2022',
    sourcemap: true,
  },
});
