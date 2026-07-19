// Flat config (ESLint 10). Minimal V0 baseline: TS type-aware lint +
// React + React Hooks rules. Strict enough to catch real bugs;
// non-pedantic so V1 dev velocity isn't burdened.
//
// React rules come from @eslint-react (the maintained flat-config successor to
// eslint-plugin-react, which never shipped ESLint 10 support). Hooks rules stay
// on the official eslint-plugin-react-hooks (ESLint-10 compatible since v6).

import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import eslintReact from '@eslint-react/eslint-plugin';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';

export default tseslint.config(
  {
    ignores: ['dist', 'node_modules', 'e2e', 'tests', 'vitest.config.ts', 'playwright.config.ts'],
  },
  {
    files: ['src/**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      ...tseslint.configs.recommended,
      eslintReact.configs['recommended-typescript'],
    ],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: { ...globals.browser, ...globals.es2022 },
    },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // react-hooks 7 promoted set-state-in-effect to an error. Our initial
      // WS-connect effect (set 'connecting', then dial the server) is a
      // deliberate, tested pattern — keep the advice visible as a warning
      // rather than a hard failure.
      'react-hooks/set-state-in-effect': 'warn',
      // TS strict already catches no-explicit-any in our config; tone down
      // lint-side to warn so codebase isn't flagged for skeleton stubs.
      '@typescript-eslint/no-explicit-any': 'warn',
      // Unused vars are caught by tsc with noUnusedLocals; allow _-prefixed
      // params (callback convention).
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      // Empty interfaces are a known stub pattern (EmptyState etc).
      '@typescript-eslint/no-empty-object-type': 'off',
    },
  },
);
