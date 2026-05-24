import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// Vite config for frontend-game.
//
// Port 5174 per spec AC-FG-3 (frontend/ owns 5173).
//
// HMR rule for src/game/** (spec AC-FG-14): when a Phaser scene file
// changes, do a controlled full-page-reload instead of letting HMR try
// to hot-swap Phaser internals (which freezes the canvas silently).
// React component edits keep normal HMR.

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@game': path.resolve(__dirname, './src/game'),
    },
  },
  server: {
    port: 5174,
    strictPort: true,
    host: 'localhost',
  },
  preview: {
    port: 5174,
    strictPort: true,
  },
  build: {
    target: 'es2022',
    sourcemap: true,
  },
});
