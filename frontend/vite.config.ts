/// <reference types="vitest/config" />
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { viteStaticCopy } from 'vite-plugin-static-copy';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [
    react(),
    viteStaticCopy({
      targets: [
        // VAD worklet + ONNX models
        { src: 'node_modules/@ricky0123/vad-web/dist/vad.worklet.bundle.min.js', dest: 'vad' },
        { src: 'node_modules/@ricky0123/vad-web/dist/silero_vad_legacy.onnx', dest: 'vad' },
        { src: 'node_modules/@ricky0123/vad-web/dist/silero_vad_v5.onnx', dest: 'vad' },
        // ONNX Runtime WASM + MJS (required for WebAssembly initialization)
        { src: 'node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.wasm', dest: 'vad' },
        { src: 'node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs', dest: 'vad' },
      ],
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5174,
    proxy: {
      // MED-8 single-domain: serve the game client under /game on THIS origin.
      // Not a convenience — localStorage is partitioned per origin, so this is
      // what lets a session (`lw_auth`) and a language (`lw_language`) chosen
      // here carry into the game with no code shared between the two apps.
      // Mirrors the prod `location /game/` block in frontend/nginx.conf.
      // `ws: true` forwards vite's HMR socket so the game still hot-reloads.
      '/game': {
        target: 'http://localhost:5176',
        changeOrigin: false,
        ws: true,
      },
      '/v1': {
        target: 'http://localhost:3123',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:3123',
        ws: true,
        changeOrigin: true,
      },
      '/languagetool': {
        target: 'http://localhost:8875',
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/languagetool/, ''),
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        // 🔴 FUNCTION form, not the object form, since vite 8 (2026-09-13). Vite 8 bundles with
        // rolldown, which accepts only a function here — the object form fails the build outright
        // with `TypeError: manualChunks is not a function`, after a softer warning
        // (`Invalid type: Expected Function but received Object`) that is easy to scroll past.
        //
        // Same grouping as before, expressed as a lookup so the mapping stays readable: the point
        // was never the syntax, it is which vendors share a chunk.
        manualChunks(id: string) {
          const GROUPS: Record<string, readonly string[]> = {
            'vendor-react': ['react', 'react-dom', 'react-router-dom'],
            'vendor-tiptap': [
              '@tiptap/react', '@tiptap/core', '@tiptap/starter-kit',
              '@tiptap/extension-placeholder', '@tiptap/extension-highlight',
            ],
            'vendor-ui': ['lucide-react', 'sonner', 'recharts'],
            'vendor-query': ['@tanstack/react-query'],
          };
          if (!id.includes('node_modules')) return undefined;
          // Match on the package boundary rather than a bare substring: `react` must not claim
          // `react-router-dom`, and the longest match wins so a scoped name beats its prefix.
          const norm = id.replace(/\\/g, '/');
          let best: string | undefined;
          let bestLen = 0;
          for (const [chunk, pkgs] of Object.entries(GROUPS)) {
            for (const pkg of pkgs) {
              if (norm.includes(`node_modules/${pkg}/`) && pkg.length > bestLen) {
                best = chunk;
                bestLen = pkg.length;
              }
            }
          }
          return best;
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    // codemirror-json-schema's ESM dist uses extensionless relative imports — node's resolver
    // (vitest external deps) chokes; inlining lets vite's resolver handle it (build/dev already do).
    server: { deps: { inline: ['codemirror-json-schema'] } },
    // Unit tests only. Playwright e2e specs live under tests/e2e and run via
    // their own runner — excluding them keeps vitest fast and its output clean
    // (they otherwise get swept in as "0 test" files).
    include: ['src/**/*.test.{ts,tsx}'],
    exclude: ['node_modules', 'dist', 'tests/e2e/**', '**/*.spec.ts'],
  },
});
