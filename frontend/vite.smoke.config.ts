// S3 smoke — serve the STATIC build on a dedicated port with the same /v1 proxy the dev server
// uses, so a live-browser screenshot/smoke is stable and immune to other sessions' HMR churn on
// :5199. NOT the app's build config — my own throwaway for `vite preview`.
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  preview: {
    port: 5210,
    proxy: {
      '/v1': { target: 'http://localhost:3123', changeOrigin: true },
      '/ws': { target: 'ws://localhost:3123', ws: true, changeOrigin: true },
    },
  },
});
