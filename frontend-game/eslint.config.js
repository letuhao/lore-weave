// Flat config (ESLint 9). Minimal V0 baseline: TS type-aware lint +
// React + React Hooks rules. Strict enough to catch real bugs;
// non-pedantic so V1 dev velocity isn't burdened.

import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';

export default tseslint.config(
  {
    ignores: ['dist', 'node_modules', 'e2e', 'tests', 'vitest.config.ts', 'playwright.config.ts'],
  },
  {
    files: ['src/**/*.{ts,tsx}'],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: { ...globals.browser, ...globals.es2022 },
    },
    plugins: { react, 'react-hooks': reactHooks },
    settings: { react: { version: 'detect' } },
    rules: {
      ...react.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      // React 17+ JSX transform — no React import required.
      'react/react-in-jsx-scope': 'off',
      'react/prop-types': 'off',
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
