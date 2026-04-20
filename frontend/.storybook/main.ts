import type { StorybookConfig } from '@storybook/react-vite';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));

// K19a.8 — Storybook 10 config for the knowledge feature.
// Addons kept lean: a11y (catches accessibility regressions on state
// cards) + docs (auto-generates prop tables from TypeScript). We
// deliberately dropped `@storybook/addon-vitest` (requires vitest 3+;
// we're still on 2), `@chromatic-com/storybook` (no Chromatic pipeline),
// and `addon-onboarding` (welcome stories — noise for a real codebase).
const config: StorybookConfig = {
  stories: ['../src/**/*.stories.@(ts|tsx)'],
  addons: ['@storybook/addon-a11y', '@storybook/addon-docs'],
  framework: '@storybook/react-vite',
  viteFinal: async (cfg) => {
    // review-impl F1 — swap `@/auth` for the MockAuthProvider so
    // components importing `useAuth` from the canonical path see the
    // stub context (stable fake token + user) instead of the real
    // AuthProvider (which fires a `/v1/me` fetch on mount and would
    // spam 404s into every story).
    //
    // Preserves the existing `@/*` alias pattern for every other path
    // by listing the specific `@/auth` resolver BEFORE the generic
    // `@/` (Vite resolves aliases top-down, first match wins).
    cfg.resolve = cfg.resolve ?? {};
    const existingAlias = cfg.resolve.alias;
    const authShim = path.resolve(here, './MockAuthProvider.tsx');
    const srcRoot = path.resolve(here, '../src');
    cfg.resolve.alias = [
      { find: /^@\/auth$/, replacement: authShim },
      { find: /^@\//, replacement: `${srcRoot}/` },
      // Keep anything the host vite.config.ts already set (array/object).
      ...(Array.isArray(existingAlias)
        ? existingAlias
        : existingAlias
          ? Object.entries(existingAlias).map(([find, replacement]) => ({
              find,
              replacement: replacement as string,
            }))
          : []),
    ];
    return cfg;
  },
};
export default config;