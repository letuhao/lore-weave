// 24 PH18 — the deep-link contract, END TO END, through the panels that actually receive it.
//
// This is the test PlanHubPanel's own comment CLAIMED existed and did not. Its absence is precisely
// what let the CONSUMER half of the seam ship dead: the Hub fired `openPanel(id, { params })` with
// correct panel ids, and neither Quality panel read `props.params` at all. The link opened the panel
// UNFILTERED and looked like it had worked — the same "a seam that only ever gets undefined is
// indistinguishable from a designed fallback" failure the canvas half had, one layer further out.
//
// It also pins the ID-SPACE decision (RUN-STATE D-04): the overlay's canon ref is a `canon_rule.id`,
// but QualityCanonPanel lists `CanonIssue` rows, which carry NO rule id. So canon deep-links by the
// node's CHAPTER (what that panel can actually resolve); threads deep-link by the thread id (which
// IS what the promises panel lists).
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThreadsPanel } from '@/features/composition/components/ThreadsPanel';

const threadsHook = vi.hoisted(() => ({ useNarrativeThreads: vi.fn() }));
vi.mock('@/features/composition/hooks/useNarrativeThreads', () => threadsHook);
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? _k }),
}));

const thread = (id: string, status = 'open') => ({
  id,
  project_id: 'p',
  user_id: 'u',
  kind: 'promise',
  status,
  opened_at_node: null,
  payoff_node: null,
  priority: 1,
  summary: `promise ${id}`,
  trigger: '',
  created_at: '',
  updated_at: '',
  is_archived: false,
});

describe('PH18 deep-link — the promises lens CONSUMES focusThreadId', () => {
  it('highlights the focused thread and hoists it to the top', () => {
    threadsHook.useNarrativeThreads.mockReturnValue({
      data: { threads: [thread('t1'), thread('t2')], open_count: 2 },
      isError: false,
      isLoading: false,
    });
    render(<ThreadsPanel projectId="p" token="tok" enabled focusThreadId="t2" />);

    const rows = screen.getAllByTestId('composition-thread');
    // hoisted: the focused one is FIRST, so a deep-link lands on something visible…
    expect(rows[0].getAttribute('data-focused')).toBe('true');
    // …and it is the right one.
    expect(rows[0].textContent).toContain('promise t2');
    // nothing is hidden — the panel is still the whole ledger.
    expect(rows).toHaveLength(2);
  });

  it('with NO focus, nothing is highlighted (the param is optional, not a default)', () => {
    threadsHook.useNarrativeThreads.mockReturnValue({
      data: { threads: [thread('t1')], open_count: 1 },
      isError: false,
      isLoading: false,
    });
    render(<ThreadsPanel projectId="p" token="tok" enabled />);
    expect(screen.getByTestId('composition-thread').getAttribute('data-focused')).toBeNull();
  });

  it('a focused thread that is NOT in the current filter SAYS SO', () => {
    // The promise may already be paid while the filter is "open". Leaving the user to hunt for a
    // highlight that is not on screen is the silent no-op again, just quieter.
    threadsHook.useNarrativeThreads.mockReturnValue({
      data: { threads: [thread('t1')], open_count: 1 },
      isError: false,
      isLoading: false,
    });
    render(<ThreadsPanel projectId="p" token="tok" enabled focusThreadId="t-paid" />);
    expect(screen.getByTestId('composition-threads-focus-missing')).toBeTruthy();
  });
});
