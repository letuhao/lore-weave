import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// R1 — the browser was autofilling the user's ACCOUNT PASSWORD into the API-key field.
//
// 🔴 FOUND BY THE NEW-USER RUN, 2026-09-04. Registered a fresh account, signed in, and opened
// Settings → Providers → Add Provider. Read straight off the live DOM:
//
//   type="url"       placeholder="https://api.example.com"   value="claude-test@loreweave.dev"
//   type="password"  placeholder="sk-..."                    value=<NONEMPTY>
//
// The saved EMAIL landed in Endpoint URL and the saved PASSWORD in API Key. None of the dialog's
// inputs declared `autocomplete`, so the browser read an adjacent text+password pair as a login
// form and filled it.
//
// ⚠️ THE HARM IS NOT COSMETIC. A user with a password manager who does not notice submits their
// own account password as a provider API key. It is then encrypted and stored as a provider
// credential — the account password now lives in a second store it was never meant to reach — and
// every provider call fails in a way that gives no hint why.
//
// `new-password` on the secret fields, not merely `off`: `off` is widely ignored by password
// managers, and `new-password` is the one token they honour as "this is NOT the saved credential".
//
// 🔴 WHY THIS IS A SOURCE SCAN AND NOT A RENDER TEST. jsdom does not autofill, so no rendering
// assertion can reproduce the defect — a `render()` test here would pass just as happily with
// every attribute deleted, which is the vacuous shape this repo's non-vacuity standard exists to
// forbid. What IS mechanically checkable is that every input in this file declares the attribute,
// and that is what the browser acts on.
const SRC = readFileSync(
  resolve(process.cwd(), 'src/features/settings/ProvidersTab.tsx'),
  'utf-8',
);

/** Attribute bodies contain `>` inside `{(e) => ...}` handlers, so a `<input[^>]*>` regex silently
 *  matches NOTHING and the check passes vacuously. It did exactly that on the first attempt. */
function inputBodies(src: string): string[] {
  return src.split('<input').slice(1).map((c) => c.split('/>')[0]);
}

describe('ProvidersTab — credential autofill', () => {
  it('finds the inputs at all (the anti-vacuity check)', () => {
    // If the file is refactored so this parser stops matching, every assertion below would pass
    // against an empty list. Pin the count so that failure is loud.
    expect(inputBodies(SRC).length).toBeGreaterThanOrEqual(8);
  });

  it('every input in both dialogs declares autoComplete', () => {
    const missing = inputBodies(SRC)
      .filter((b) => !b.includes('autoComplete'))
      .map((b) => /value=\{([^}]+)\}/.exec(b)?.[1] ?? b.trim().slice(0, 40));
    expect(missing, `inputs with no autoComplete: ${missing.join(', ')}`).toEqual([]);
  });

  it('🔴 the API-key fields use new-password, not merely off', () => {
    // The measured defect. `off` alone does not stop a password manager; this is the assertion
    // that would have caught the live DOM state.
    const secrets = inputBodies(SRC).filter((b) => b.includes('type="password"'));
    expect(secrets.length, 'expected the add + edit API-key fields').toBe(2);
    for (const s of secrets) {
      expect(s).toContain('autoComplete="new-password"');
    }
  });

  it('the endpoint URL field does not invite an email', () => {
    // The other half of the measured state: the saved email landed in the endpoint field.
    const url = inputBodies(SRC).find((b) => b.includes('type="url"'));
    expect(url).toBeTruthy();
    expect(url).toContain('autoComplete="off"');
  });
});
