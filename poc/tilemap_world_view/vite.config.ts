import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  // VITE_LLM_ENDPOINT defaults to lmstudio. User can override via .env.local:
  //   VITE_LLM_ENDPOINT=http://localhost:1234
  const env = loadEnv(mode, process.cwd(), '');
  const llmTarget = env.VITE_LLM_ENDPOINT || 'http://localhost:1234';

  return {
    base: './',
    server: {
      port: 5174,
      open: false,
      host: 'localhost',
      proxy: {
        // Proxy /api/llm/* → <llmTarget>/v1/* (lmstudio default; OpenAI-compatible)
        // Avoids CORS issues when frontend calls LLM endpoint cross-origin.
        '/api/llm': {
          target: llmTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/llm/, '/v1'),
          timeout: 120000,
        },
      },
    },
    build: {
      target: 'es2020',
      sourcemap: true,
      chunkSizeWarningLimit: 1500,
    },
    test: {
      environment: 'node',
      globals: false,
    },
  };
});
