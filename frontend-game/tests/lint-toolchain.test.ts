// The linter must be able to LOAD.
//
// This exists because it already happened: TypeScript was upgraded to 7.0.2
// (PR #157, "upgrade TypeScript to 7 (vite projects)") and every ESLint run in
// the pnpm workspace died — not on a rule, but at module load:
//
//   TypeError: Cannot read properties of undefined (reading 'Cjs')
//     at @typescript-eslint/typescript-estree/dist/create-program/shared.js:59
//
// TypeScript 7 is the native (Go) port. Its package main export is
// `lib/version.cjs` — a version string. The classic `ts.*` compiler API that
// typescript-estree is built on does not exist there at all; the replacement
// lives behind `./unstable/*` with a completely different shape. So this is not
// a version-range nit that a typescript-eslint bump fixes: as of writing, the
// newest typescript-eslint (8.65.0) still declares `typescript >=4.8.4 <6.1.0`.
//
// Nothing caught it. `tsc --noEmit` kept passing (the native tsc works fine),
// tests kept passing, and lint silently stopped existing for months. That is
// the "adjacent decision defeats it" shape: two individually-correct decisions
// where one quietly removes another's guarantee.
//
// So this test asserts the CAPABILITY, not a version number. If typescript-eslint
// ever does support the native port, this passes on TypeScript 7 with no edit —
// a version-pin assertion would have to be remembered and relaxed by hand.

import { describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require_ = createRequire(import.meta.url);

describe('lint toolchain', () => {
  it('exposes the classic TypeScript compiler API that typescript-estree needs', () => {
    const ts = require_('typescript') as Record<string, unknown>;
    // `ts.Extension` is the exact symbol whose absence threw. Checking it by
    // name keeps the failure message pointing at the real cause instead of a
    // generic "lint broke".
    expect(typeof ts.Extension, 'typescript must expose the classic ts.* API').not.toBe(
      'undefined',
    );
    expect(typeof ts.createProgram).toBe('function');
  });

  it('can load the ESLint TypeScript parser without throwing', () => {
    // The real property under test: does the linter start at all? An unloadable
    // parser means zero files are linted while every command still exits 0 in
    // some setups — coverage reported, nothing checked.
    expect(() => require_('@typescript-eslint/typescript-estree')).not.toThrow();
    expect(() => require_('@typescript-eslint/parser')).not.toThrow();
  });
});
