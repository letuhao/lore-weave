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
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          'vendor-tiptap': [
            '@tiptap/react', '@tiptap/core', '@tiptap/starter-kit',
            '@tiptap/extension-placeholder', '@tiptap/extension-highlight',
          ],
          'vendor-ui': ['lucide-react', 'sonner', 'recharts'],
          'vendor-query': ['@tanstack/react-query'],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
  },
});
