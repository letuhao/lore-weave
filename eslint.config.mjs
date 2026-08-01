// Workspace-wide flat config (ESLint 10) — the SINGLE lint config for the pnpm
// workspace (frontend-game + packages/*). The novel-workflow `frontend/` is
// outside this workspace (pnpm-workspace.yaml, spec §1 #5) and keeps its own.
//
// WHY IT LIVES AT THE ROOT. The previous config sat in `frontend-game/` and
// declared `files: ['src/**/*.{ts,tsx}']` with `ignores: [..., 'tests', ...]`.
// Everything outside that one directory was therefore DEFAULT-UNCOVERED —
// `packages/auth-client` and `packages/i18n` had no config and no lint script,
// so several hundred lines of shipped code had never been linted at all, and
// neither had a single test file. That is the "scope never reaches it" shape in
// docs/standards/non-vacuity.md: the check exists, reports success, and simply
// does not look at most of the tree. New packages join automatically here
// because the glob is `packages/*/src`, not an enumerated list.
//
// Three scopes, deliberately different:
//   1. every workspace TS file  — the shared TypeScript baseline
//   2. frontend-game/src        — + React and hooks rules (the only React code)
//   3. tests                    — + test globals, and the assertions relaxed
//      that only make sense in production code

import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import eslintReact from '@eslint-react/eslint-plugin';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';

export default tseslint.config(
  {
    ignores: [
      '**/dist/**',
      '**/node_modules/**',
      '**/.pnpm/**',
      // Agent worktrees hold full copies of frontend-game. Beyond being noise,
      // their tsconfigs make `tsconfigRootDir` ambiguous and every parse fails.
      '.claude/**',
      'frontend-game/e2e/**', // Playwright specs, a different tsconfig
      '**/*.config.{js,ts}',
      '**/*.tsbuildinfo',
    ],
  },

  // ── 1. shared TypeScript baseline — ALL workspace TS ──────────────────
  {
    files: ['frontend-game/{src,tests}/**/*.{ts,tsx}', 'packages/*/src/**/*.{ts,tsx}'],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: { ...globals.browser, ...globals.es2022 },
      // Pin the root explicitly. Without it the parser finds several candidate
      // roots (this repo plus every .claude worktree copy of frontend-game) and
      // refuses to guess — every file then fails with a parse error rather than
      // a lint finding, which reads like "the code is broken" instead of "the
      // config is ambiguous".
      parserOptions: { tsconfigRootDir: import.meta.dirname },
    },
    rules: {
      // tsc already errors on these under `strict`; keep lint advisory so the
      // signal here stays "things tsc cannot see".
      '@typescript-eslint/no-explicit-any': 'warn',
      // `_`-prefixed params are the callback convention; tsc's noUnusedLocals
      // is the real gate.
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      // Empty interfaces are a legitimate stub/extension pattern.
      '@typescript-eslint/no-empty-object-type': 'off',
    },
  },

  // ── 2. React — frontend-game/src only ─────────────────────────────────
  // packages/* are framework-free on purpose (auth-client and i18n are consumed
  // by React but contain none), so applying React rules there would be noise.
  {
    files: ['frontend-game/src/**/*.{ts,tsx}'],
    extends: [eslintReact.configs['recommended-typescript']],
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // react-hooks 7 promoted this to an error. The WS-connect effect (set
      // 'connecting', then dial) is a deliberate, tested pattern — keep the
      // advice visible without failing the build.
      'react-hooks/set-state-in-effect': 'warn',
    },
  },

  // ── 3. tests ──────────────────────────────────────────────────────────
  {
    files: ['frontend-game/tests/**/*.{ts,tsx}'],
    languageOptions: {
      globals: { ...globals.node, ...globals.browser },
    },
    rules: {
      // Tests deliberately construct malformed input and stub globals with
      // partial shapes; `any` there is a tool, not a smell.
      '@typescript-eslint/no-explicit-any': 'off',
      // Contract tests assert against literal wire payloads.
      '@typescript-eslint/no-non-null-assertion': 'off',
    },
  },
);
