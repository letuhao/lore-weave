import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

// R6 — the turn that dies before the model answers, and leaves the author staring at their own words.
//
// 🔴 MEASURED LIVE, 2026-09-04, while testing a deliberately-stalling provider. The turn failed in
// the context preflight — the backend knew exactly why:
//
//     LLMInvalidRequest: the assembled prompt overflows this model's context window:
//     input=9732 + safety=1228 = 10960 > context_length=8192
//
// The author saw their own message at 7:17:21 PM and **nothing else**. No assistant bubble, no
// badge, no error.
//
// 🔴 WHY D2's BADGE CANNOT COVER THIS, which is the whole reason this file exists. D2 badges an
// EMPTY ASSISTANT MESSAGE. Here `CP-0.4 orphaned turn: no assistant row` means none was ever
// written — the failure is stamped on the USER message instead. Two different mechanisms with the
// same author experience:
//
//     V3 (D2)   assistant row exists, empty      -> message-empty-turn-badge
//     R6        assistant row DOES NOT EXIST     -> nothing to render on, until now
//
// Same promise as D2: this is CHROME. Nothing is written into any message's content, and the
// owner's declined generic-failure-LINE stands untouched.

vi.mock('react-i18next', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useTranslation: () => ({
    t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k,
    i18n: { language: 'en', changeLanguage: () => Promise.resolve() },
  }),
}));

import { UserMessage } from '../UserMessage';

const BADGE = 'message-orphaned-turn-badge';

describe('UserMessage — the orphaned turn', () => {
  it('badges a user message whose turn died before any reply', () => {
    render(<UserMessage content="Say hello." outcome="failed" />);
    expect(screen.getByTestId(BADGE)).toBeTruthy();
  });

  it('🔴 says nothing on an ordinary message', () => {
    // The arm that matters most: every message a user has ever sent renders through here.
    render(<UserMessage content="Say hello." />);
    expect(screen.queryByTestId(BADGE)).toBeNull();
  });

  it('🔴 says nothing when the turn completed', () => {
    render(<UserMessage content="Say hello." outcome="completed" />);
    expect(screen.queryByTestId(BADGE)).toBeNull();
  });

  it('🔴 says nothing while the turn is still waiting on the user', () => {
    // `awaiting_input` is a live Tier-A approval card, not a failure. Badging it would tell the
    // author their work was lost while the card sits there waiting for a click — and a pending
    // card reading as a hang is a mistake this project has already made four times.
    render(<UserMessage content="Say hello." outcome="awaiting_input" />);
    expect(screen.queryByTestId(BADGE)).toBeNull();
  });

  it('says nothing is CHANGED, and does not claim to know why', () => {
    // Same wording discipline as D2. The runtime knows no reply arrived; it does NOT know whether
    // that was a crash, a refusal or a slow provider, and the owner declined a line that guesses.
    render(<UserMessage content="Say hello." outcome="failed" />);
    const text = screen.getByTestId(BADGE).textContent ?? '';
    expect(text).toContain('nothing was changed');
    expect(text.toLowerCase()).not.toContain('crash');
  });

  it('🔴 the key is registered in every locale, and not echoed', () => {
    // A missing key renders the raw `message.orphaned_turn` to a non-English author.
    const mods = import.meta.glob('../../../../i18n/locales/*/chat.json', { eager: true }) as
      Record<string, { default: Record<string, Record<string, string>> }>;
    const paths = Object.keys(mods);
    expect(paths.length).toBeGreaterThanOrEqual(18);
    const en = mods[paths.find((p) => p.includes('/en/'))!].default.message.orphaned_turn;
    expect(en).toBeTruthy();
    for (const path of paths) {
      const locale = path.split('/').slice(-2)[0];
      const v = mods[path].default?.message?.orphaned_turn;
      expect(v, `${locale} is missing message.orphaned_turn`).toBeTruthy();
      if (locale !== 'en') expect(v, `${locale} echoes English`).not.toBe(en);
    }
  });
});
