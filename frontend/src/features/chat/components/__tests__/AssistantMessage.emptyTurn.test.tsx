import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

// D2 (owner, 2026-09-04) — THE BLANK BUBBLE.
//
// 🔴 MEASURED LIVE. A turn that failed before the model produced anything rendered as literally
// nothing: no text, no badge, no error. The author sees an empty bubble reading `↑0 ↓0 · 4.2s`
// and retries by instinct. Across the live store, assistant rows with no content, no tool calls
// and no card run at ~0.11% of turns — 7 of 6,640 in August, 1 of 625 in September.
//
// ⚠️ WHY THIS IS CHROME AND NOT MESSAGE TEXT, which is the only reason it may exist at all. The
// owner DECLINED a generic failure line in the assistant's own words — recorded in
// `_last_tool_error_for_author`: "a blank turn cannot be told apart from a crash, a refusal or a
// slow turn". That decision STANDS. Nothing is written into `content`, no runtime-authored prose
// enters the transcript, and the stored message is untouched; this is the same badge affordance
// the interrupted/errored turns already use, extended to the case that renders as nothing.
//
// ⚠️ AND WHY IT IS NOT THE UPSTREAM FIX. The first plan was to re-classify provider-registry's
// `status` so the existing DQ-T33 machinery would have a real error to surface. The measurement
// killed it: that discriminator selects 177 `usage_logs` rows against 1 `chat_messages` row in the
// same window, because `usage_logs` counts LLM CALLS (every pass, plus subagents and enrichment
// using purpose='chat') and `chat_messages` counts TURNS. 177 rows flipped to catch 1.

// t() must resolve to the SHIPPED English string, not the key, or the wording assertion below
// would pass against 'message.empty_turn' and prove nothing about what an author reads.
vi.mock('react-i18next', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useTranslation: () => ({
    t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k,
    i18n: { language: 'en', changeLanguage: () => Promise.resolve() },
  }),
}));

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok-1' }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const { submitMessageFeedback } = vi.hoisted(() => ({ submitMessageFeedback: vi.fn() }));
vi.mock('../../api', () => ({ chatApi: { submitMessageFeedback } }));

import { AssistantMessage } from '../AssistantMessage';

const BADGE = 'message-empty-turn-badge';

describe('AssistantMessage — the empty turn', () => {
  it('badges the measured shape: no content, no tools, finished normally', () => {
    // The exact row from the live run: content '', 0 tool calls, finish_reason 'stop',
    // input_tokens 0, output_tokens 0. Stored outcome was already 'failed'; the author saw
    // nothing at all.
    render(
      <AssistantMessage
        content=""
        messageId="m1"
        finishReason="stop"
        inputTokens={0}
        outputTokens={0}
      />,
    );
    expect(screen.getByTestId(BADGE)).toBeTruthy();
  });

  it('🔴 says nothing on an ordinary reply', () => {
    // The arm that matters most: this must never appear on a working turn.
    render(<AssistantMessage content="Here is your chapter." messageId="m1" finishReason="stop" />);
    expect(screen.queryByTestId(BADGE)).toBeNull();
  });

  it('🔴 says nothing while the reply is still streaming', () => {
    // Content is legitimately empty at the first frame of every single turn. A badge here would
    // flash on EVERY reply, which is worse than the defect it fixes.
    render(<AssistantMessage content="" messageId="m1" isStreaming />);
    expect(screen.queryByTestId(BADGE)).toBeNull();
  });

  it('🔴 says nothing when the turn CALLED something', () => {
    // A turn that ran a tool said something by doing, and its result renders below. This guard is
    // for the turn that did nothing at all.
    render(
      <AssistantMessage
        content=""
        messageId="m1"
        finishReason="stop"
        toolCalls={[{ tool: 'book_list', ok: true } as never]}
      />,
    );
    expect(screen.queryByTestId(BADGE)).toBeNull();
  });

  it('🔴 says nothing when the turn produced reasoning', () => {
    // A thinking-only turn has visible output of its own, and ThinkingBlock already carries a
    // stuck-warning for exactly that case (`contentEmpty` with >200 chars of reasoning). Two
    // badges on one message would be the runtime talking over itself.
    render(<AssistantMessage content="" messageId="m1" finishReason="stop" reasoning="thinking..." />);
    expect(screen.queryByTestId(BADGE)).toBeNull();
  });

  it('🔴 does not double-badge an interrupted or errored turn', () => {
    // Those have their own `message-incomplete-badge` directly above this one and are a different
    // story to tell: the turn produced partial work and stopped, rather than producing nothing.
    for (const fr of ['interrupted', 'error']) {
      const { unmount } = render(
        <AssistantMessage content="" messageId="m1" finishReason={fr} />,
      );
      expect(screen.queryByTestId(BADGE)).toBeNull();
      expect(screen.getByTestId('message-incomplete-badge')).toBeTruthy();
      unmount();
    }
  });

  it('says nothing is CHANGED, not what went wrong', () => {
    // The wording is load-bearing. The owner declined a line that DIAGNOSES a blank turn, because
    // a crash, a refusal and a slow turn are indistinguishable from here. What this asserts is only
    // what the runtime actually knows: no reply arrived, and therefore nothing was written.
    render(<AssistantMessage content="" messageId="m1" finishReason="stop" />);
    const text = screen.getByTestId(BADGE).textContent ?? '';
    expect(text).toContain('nothing was changed');
    // It must not claim to know the cause.
    expect(text.toLowerCase()).not.toContain('crash');
    expect(text.toLowerCase()).not.toContain('error');
  });
});

// 🔴 THE KEY MUST EXIST IN EVERY LOCALE, or an author outside English reads the raw key. The
// sibling badge (`message.incomplete_error`) is present in all 18, and the repo tracks MISSING and
// ECHOED separately in locales/AUDIT.md — a copy of the English string counts as a defect there,
// so these are real translations rather than fallbacks.
describe('message.empty_turn is registered', () => {
  it('exists, is non-empty, and is not echoed English outside en', async () => {
    const mods = import.meta.glob('../../../../i18n/locales/*/chat.json', { eager: true }) as
      Record<string, { default: Record<string, Record<string, string>> }>;
    const paths = Object.keys(mods);
    expect(paths.length).toBeGreaterThanOrEqual(18);

    const en = mods[paths.find((p) => p.includes('/en/'))!].default.message.empty_turn;
    expect(en).toBeTruthy();

    for (const path of paths) {
      const locale = path.split('/').slice(-2)[0];
      const value = mods[path].default?.message?.empty_turn;
      expect(value, `${locale} is missing message.empty_turn`).toBeTruthy();
      if (locale !== 'en') {
        expect(value, `${locale} echoes the English string`).not.toBe(en);
      }
    }
  });
});
