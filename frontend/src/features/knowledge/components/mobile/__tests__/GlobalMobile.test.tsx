import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

const useSummariesMock = vi.fn();
vi.mock('../../../hooks/useSummaries', () => ({
  useSummaries: () => useSummariesMock(),
}));

// Sonner toast is side-effect only in these tests.
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { GlobalMobile } from '../GlobalMobile';

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

interface HookReturn {
  global: { content: string; version: number } | null;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  updateGlobal: ReturnType<typeof vi.fn>;
  isUpdatingGlobal: boolean;
}

function makeHookReturn(overrides: Partial<HookReturn> = {}): HookReturn {
  return {
    global: { content: 'existing bio', version: 3 },
    isLoading: false,
    isError: false,
    error: null,
    updateGlobal: vi.fn().mockResolvedValue(undefined),
    isUpdatingGlobal: false,
    ...overrides,
  };
}

/** Build a proper ``Error`` shape that the production
 *  ``isVersionConflict`` type guard accepts: Error instance with
 *  ``.status = 412`` and ``.body`` carrying the server's current
 *  Summary. The guard reassigns ``body`` → ``current`` on the error,
 *  which the 412 branch reads to absorb baseline state. The initial
 *  test used a plain object that failed ``err instanceof Error`` so
 *  the whole 412 path never ran — review-impl HIGH. */
function makeConflictError(
  current: { content: string; version: number },
): Error {
  return Object.assign(new Error('version conflict'), {
    status: 412,
    body: current,
  });
}

describe('GlobalMobile', () => {
  beforeEach(() => {
    useSummariesMock.mockReset();
  });

  it('renders the textarea with existing content, disables Save when clean, and applies TOUCH_TARGET_CLASS', async () => {
    useSummariesMock.mockReturnValue(makeHookReturn());
    render(<GlobalMobile />, { wrapper: Wrapper });
    const textarea = await screen.findByTestId('mobile-global-textarea') as HTMLTextAreaElement;
    // The sync effect fires after mount; wait for it to populate.
    await waitFor(() => {
      expect(textarea.value).toBe('existing bio');
    });
    const save = screen.getByTestId('mobile-global-save') as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    // Dirty badge not shown on clean state.
    expect(screen.queryByTestId('mobile-global-unsaved')).toBeNull();
    // Review-impl L2: lock the 44px minimum tap target. A regression
    // that dropped TOUCH_TARGET_CLASS from the cn() composition
    // would silently ship a ~32px-tall save button on phones and
    // defeat the K19f.5 audit groundwork.
    expect(save.className).toContain('min-h-[44px]');
  });

  it('enables Save + shows Unsaved badge when user edits + calls updateGlobal with expectedVersion', async () => {
    const updateGlobal = vi.fn().mockResolvedValue(undefined);
    useSummariesMock.mockReturnValue(
      makeHookReturn({ updateGlobal }),
    );
    render(<GlobalMobile />, { wrapper: Wrapper });
    const textarea = await screen.findByTestId('mobile-global-textarea') as HTMLTextAreaElement;
    await waitFor(() => {
      expect(textarea.value).toBe('existing bio');
    });
    fireEvent.change(textarea, { target: { value: 'edited bio' } });
    await screen.findByTestId('mobile-global-unsaved');
    const save = screen.getByTestId('mobile-global-save') as HTMLButtonElement;
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    await waitFor(() => {
      expect(updateGlobal).toHaveBeenCalledWith({
        payload: { content: 'edited bio' },
        expectedVersion: 3,
      });
    });
  });

  it('surfaces load errors via the error banner', () => {
    useSummariesMock.mockReturnValue(
      makeHookReturn({
        isError: true,
        error: new Error('network down'),
        global: null,
      }),
    );
    render(<GlobalMobile />, { wrapper: Wrapper });
    expect(screen.getByTestId('mobile-global-error')).toBeTruthy();
    // Textarea should NOT render while error surfaces.
    expect(screen.queryByTestId('mobile-global-textarea')).toBeNull();
  });

  it('absorbs 412 conflict by advancing baselineVersion from error.body (If-Match correctness — review-impl HIGH)', async () => {
    // Regression lock for the K19f.4 design decision to KEEP If-Match
    // conflict handling on mobile. Drop it and a mobile save on top
    // of a stale baseline would silently stomp the desktop edit.
    //
    // The STRONG signal that the 412 branch actually ran: a second
    // save must send `expectedVersion: 4` (the server's updated
    // version) instead of `3` (the original). If the branch didn't
    // run, `baselineVersion` stays 3 and the retry would send 3 —
    // which would 412-loop forever in production.
    //
    // First call 412s. Second call succeeds (baseline absorbed).
    const updateGlobal = vi
      .fn()
      .mockRejectedValueOnce(
        makeConflictError({ content: 'desktop-newer', version: 4 }),
      )
      .mockResolvedValueOnce(undefined);
    useSummariesMock.mockReturnValue(makeHookReturn({ updateGlobal }));
    render(<GlobalMobile />, { wrapper: Wrapper });
    const textarea = (await screen.findByTestId(
      'mobile-global-textarea',
    )) as HTMLTextAreaElement;
    await waitFor(() => {
      expect(textarea.value).toBe('existing bio');
    });
    fireEvent.change(textarea, { target: { value: 'my edit' } });
    await screen.findByTestId('mobile-global-unsaved');
    // First save → 412.
    fireEvent.click(screen.getByTestId('mobile-global-save'));
    await waitFor(() => {
      expect(updateGlobal).toHaveBeenCalledTimes(1);
    });
    // First call used expectedVersion=3 (the stale baseline).
    expect(updateGlobal.mock.calls[0][0]).toEqual({
      payload: { content: 'my edit' },
      expectedVersion: 3,
    });
    // Textarea still shows the user's edit — 412 must NOT stomp local
    // content. (Re-assertion after the async toast path.)
    expect(textarea.value).toBe('my edit');
    // Unsaved badge still shows — baseline now 'desktop-newer' but
    // local is 'my edit', so dirty.
    expect(screen.getByTestId('mobile-global-unsaved')).toBeTruthy();

    // Now the real regression check: second save must ride the
    // ABSORBED baseline version (4), not the stale 3. If the 412
    // branch didn't run, expectedVersion would still be 3 and a
    // regression that deleted `setBaselineVersion(err.current.version)`
    // would fail this assertion.
    fireEvent.click(screen.getByTestId('mobile-global-save'));
    await waitFor(() => {
      expect(updateGlobal).toHaveBeenCalledTimes(2);
    });
    expect(updateGlobal.mock.calls[1][0]).toEqual({
      payload: { content: 'my edit' },
      expectedVersion: 4,
    });
  });

  it('saves an empty payload when the textarea is whitespace-only (clear intent)', async () => {
    // Review-impl LOW #3: the `trimmed === '' ? '' : content` branch
    // lets a user clear the bio by wiping the textarea. Untested on
    // desktop too, but this locks the mobile contract.
    const updateGlobal = vi.fn().mockResolvedValue(undefined);
    useSummariesMock.mockReturnValue(makeHookReturn({ updateGlobal }));
    render(<GlobalMobile />, { wrapper: Wrapper });
    const textarea = (await screen.findByTestId(
      'mobile-global-textarea',
    )) as HTMLTextAreaElement;
    await waitFor(() => {
      expect(textarea.value).toBe('existing bio');
    });
    fireEvent.change(textarea, { target: { value: '   ' } });
    await screen.findByTestId('mobile-global-unsaved');
    fireEvent.click(screen.getByTestId('mobile-global-save'));
    await waitFor(() => {
      expect(updateGlobal).toHaveBeenCalled();
    });
    // Whitespace-only coerces to empty string on save — not '   '.
    expect(updateGlobal.mock.calls[0][0]).toEqual({
      payload: { content: '' },
      expectedVersion: 3,
    });
  });
});
