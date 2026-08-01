// The two-sided auth-storage contract, machine-checked.
//
// WHY THIS EXISTS. The account is shared between the two SPAs at the database
// layer (one auth-service, one `users` table), but the SESSION is shared only
// because both apps agree on a localStorage key and a token shape. And they
// agree by NOTHING BUT COINCIDENCE: `frontend/` is deliberately outside the
// pnpm workspace (pnpm-workspace.yaml, spec §1 #5), so it CANNOT import
// `@loreweave/auth-client`. It hardcodes the same literals in its own source.
//
// That is the drift shape the repo has been bitten by before: two ends that
// agree with each other but not with a contract, each side green in its own
// unit tests, broken only in the live loop. Here the symptom would be silent
// and awful — a user logs into the novel app, opens the game, and is asked to
// log in again, with no error anywhere.
//
// So this test reads the OTHER app's source off disk and asserts the literals
// still line up. `frontend/` is not ours to import, but it IS ours to read.
//
// Bite-test (NV — a check that cannot fail is not a check): change
// AUTH_STORAGE_KEY in packages/auth-client/src/contract.ts from 'lw_auth' to
// 'lw_auth_x' and this file reds on the first assertion.

import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

import {
  AUTH_STORAGE_KEY,
  USER_STORAGE_KEY,
  AUTH_REFRESHED_EVENT,
  AUTH_REFRESHING_EVENT,
  PASSWORD_MIN_LENGTH,
  checkPassword,
} from '@loreweave/auth-client';
import { GAME_LOCALES, LANGUAGE_STORAGE_KEY, LOCALE_LABELS } from '@loreweave/i18n';

const REPO_ROOT = path.resolve(__dirname, '../..');
const NOVEL_API = path.join(REPO_ROOT, 'frontend/src/api.ts');
const NOVEL_AUTH = path.join(REPO_ROOT, 'frontend/src/auth.tsx');
const NOVEL_I18N = path.join(REPO_ROOT, 'frontend/src/i18n/index.ts');
const NOVEL_LANGUAGES = path.join(REPO_ROOT, 'frontend/src/lib/languages.ts');

function read(file: string): string {
  return readFileSync(file, 'utf8');
}

describe('auth storage contract shared with the novel-workflow frontend/', () => {
  // If `frontend/` is ever moved or renamed, this suite must FAIL rather than
  // quietly pass on zero files — a vacuous green here would be worse than no
  // test, because it reports the contract is held while checking nothing.
  it('can see both sides of the contract', () => {
    expect(existsSync(NOVEL_API), `missing ${NOVEL_API}`).toBe(true);
    expect(existsSync(NOVEL_AUTH), `missing ${NOVEL_AUTH}`).toBe(true);
  });

  it('agrees on the token storage key', () => {
    expect(AUTH_STORAGE_KEY).toBe('lw_auth');
    // Declared identically on both novel-app sides.
    expect(read(NOVEL_API)).toContain(`const AUTH_KEY = '${AUTH_STORAGE_KEY}'`);
    expect(read(NOVEL_AUTH)).toContain(`const AUTH_KEY = '${AUTH_STORAGE_KEY}'`);
  });

  it('agrees on the profile storage key', () => {
    expect(USER_STORAGE_KEY).toBe('lw_user');
    expect(read(NOVEL_AUTH)).toContain(`const USER_KEY = '${USER_STORAGE_KEY}'`);
  });

  it('agrees on the stored token field names', () => {
    // The asymmetry that makes this worth pinning: the WIRE is snake_case,
    // the STORAGE is camelCase. Writing `access_token` into localStorage would
    // typecheck fine on our side and be invisible to the novel app.
    const api = read(NOVEL_API);
    expect(api).toContain('accessToken: data.access_token');
    expect(api).toContain('refreshToken: data.refresh_token');
  });

  it('agrees on the same-tab refresh notification event', () => {
    // Cross-tab sync rides `storage`, which does NOT fire in the writing tab.
    // If these names drift, the app that refreshed keeps serving a stale token
    // to its own components.
    expect(read(NOVEL_API)).toContain(`CustomEvent('${AUTH_REFRESHED_EVENT}')`);
    expect(read(NOVEL_AUTH)).toContain(`'${AUTH_REFRESHED_EVENT}'`);
  });

  it('agrees on the refresh-in-progress event', () => {
    expect(read(NOVEL_API)).toContain(`CustomEvent('${AUTH_REFRESHING_EVENT}'`);
  });

  it('agrees on the refresh endpoint and its wire field', () => {
    const api = read(NOVEL_API);
    expect(api).toContain('/v1/auth/refresh');
    // Refresh token travels in the BODY as snake_case, not a header/cookie.
    expect(api).toContain('refresh_token: refreshToken');
  });

  it('confirms the novel app listens for cross-tab session changes', () => {
    // This listener IS the SSO channel in the other direction: our login must
    // be observable by the novel app without either importing the other.
    expect(read(NOVEL_AUTH)).toContain(`addEventListener('storage'`);
  });
});

describe('password policy mirrored from auth-service', () => {
  // The client copy exists only so the user learns WHICH rule they broke — the
  // server's 400 is one opaque "invalid email or password policy". A client
  // that is STRICTER than the server rejects passwords the server would accept;
  // one that is LOOSER promises success and then 400s. Both are user-visible
  // lies, so pin the two together.
  const AUTH_UTIL = path.join(REPO_ROOT, 'services/auth-service/internal/api/util.go');
  const AUTH_CONFIG = path.join(REPO_ROOT, 'services/auth-service/internal/config/config.go');

  it('can see the authoritative Go implementation', () => {
    expect(existsSync(AUTH_UTIL), `missing ${AUTH_UTIL}`).toBe(true);
  });

  it('matches the server minimum length', () => {
    expect(read(AUTH_CONFIG)).toContain(`getInt("PASSWORD_MIN_LENGTH", ${PASSWORD_MIN_LENGTH})`);
  });

  it('checks the same two character classes the server does', () => {
    const util = read(AUTH_UTIL);
    // `unicode.IsLetter` / `unicode.IsDigit` — NOT ASCII ranges. Our regexes use
    // \p{L} and \p{Nd} to match; an [a-z]/[0-9] client check would reject a
    // non-Latin password the server accepts.
    expect(util).toContain('unicode.IsLetter');
    expect(util).toContain('unicode.IsDigit');
    expect(util).toContain(`len(pw) < minLen`);
  });

  it('agrees with the server on concrete passwords', () => {
    expect(checkPassword('abc')).toContain('too_short');
    expect(checkPassword('abcdefgh')).toContain('needs_digit');
    expect(checkPassword('12345678')).toContain('needs_letter');
    expect(checkPassword('GameTest2026')).toEqual([]); // accepted live, HTTP 201
    // Unicode letters count, exactly as unicode.IsLetter does.
    expect(checkPassword('日本語パス1234')).toEqual([]);
  });
});

describe('language storage contract shared with the novel-workflow frontend/', () => {
  it('can see the novel app’s i18n bootstrap', () => {
    expect(existsSync(NOVEL_I18N), `missing ${NOVEL_I18N}`).toBe(true);
  });

  it('derives its locale set + endonyms from the Registry SoT, not a second list', () => {
    // ML-6: `frontend/src/lib/languages.ts` (LANGUAGE_REGISTRY) is the declared
    // SoT for the UI-locale set and each language's endonym/script/dir.
    // `packages/i18n` cannot import it (different workspace, spec §1 #5), so it
    // restates GAME_LOCALES + LOCALE_LABELS by hand — a second source of truth
    // for the same facts. They agree today only because they were copied; this
    // pins them so a registry edit cannot silently leave the game behind.
    const registry = read(NOVEL_LANGUAGES);
    for (const code of GAME_LOCALES) {
      // Every game locale must be a declared UI locale upstream — shipping one
      // the platform does not recognise would strand it outside the translation
      // pipeline entirely.
      const row = new RegExp(`\\{\\s*code:\\s*'${code}'[^}]*\\}`).exec(registry)?.[0];
      expect(row, `no LANGUAGE_REGISTRY row for '${code}'`).toBeTruthy();
      expect(row, `'${code}' is not marked uiLocale in the registry`).toContain('uiLocale: true');
      expect(row, `endonym drift for '${code}'`).toContain(`endonym: '${LOCALE_LABELS[code]}'`);
    }
  });

  it('agrees on the language storage key', () => {
    // Same mechanism as the session: one origin, one localStorage, so picking
    // a language in either app carries into the other. Drift here is silent —
    // both apps keep working, each in its own language, which is exactly the
    // kind of bug nobody files.
    expect(LANGUAGE_STORAGE_KEY).toBe('lw_language');
    expect(read(NOVEL_I18N)).toContain(`lookupLocalStorage: '${LANGUAGE_STORAGE_KEY}'`);
  });
});
