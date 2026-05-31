// Minimal ESLint — intentionally scoped to the ONE rule that catches the bug
// class that crashed EntityEditorModal live (hooks called after an early
// return). `exhaustive-deps` is deliberately left OFF for now: it's noisy
// across the existing codebase and is a separate cleanup. Expand later.
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';

export default tseslint.config(
  {
    ignores: ['dist/**', 'node_modules/**', 'storybook-static/**', 'tests/e2e/**'],
  },
  {
    files: ['src/**/*.{ts,tsx}'],
    // Don't flag the stale `// eslint-disable react-hooks/exhaustive-deps` /
    // `@typescript-eslint/*` comments left from a previously-removed eslint setup.
    linterOptions: { reportUnusedDisableDirectives: 'off' },
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    // @typescript-eslint registered (rules off) only so existing disable-comments
    // that reference its rules don't error as "rule definition not found".
    plugins: { 'react-hooks': reactHooks, '@typescript-eslint': tseslint.plugin },
    rules: {
      'react-hooks/rules-of-hooks': 'error',
    },
  },
);
