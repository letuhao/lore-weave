/// <reference types="vitest/config" />
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
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
