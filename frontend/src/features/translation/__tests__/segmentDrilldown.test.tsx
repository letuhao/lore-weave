import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/languages', () => ({ getLanguageName: (l: string) => l }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, o?: Record<string, unknown>) => (o && 'count' in o ? `${k}:${o.count}` : k),
  }),
}));

const getSegmentStatus = vi.fn();
const retranslateDirty = vi.fn();
vi.mock('../api', () => ({
  translationApi: {
    getSegmentStatus: (...a: unknown[]) => getSegmentStatus(...a),
    retranslateDirty: (...a: unknown[]) => retranslateDirty(...a),
  },
}));

import { SegmentDrilldownModal } from '../components/SegmentDrilldownModal';

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const seg = (
  i: number,
  o: Partial<{ dirty: boolean; stale: boolean; translated: boolean; needs: boolean }> = {},
) => ({
  segment_index: i, start_block_index: i, end_block_index: i, token_estimate: 10,
  translated: o.translated ?? true, dirty: !!o.dirty, stale: !!o.stale, needs: !!o.needs,
  translated_at: null,
});

describe('SegmentDrilldownModal', () => {
  beforeEach(() => { getSegmentStatus.mockReset(); retranslateDirty.mockReset(); });

  it('renders nothing when target is null', () => {
    const { container } = wrap(<SegmentDrilldownModal bookId="b" target={null} onClose={() => {}} />);
    expect(container.textContent).toBe('');
  });

  it('lists segments and re-translates the changed ones', async () => {
    getSegmentStatus.mockResolvedValue({
      chapter_id: 'ch', target_language: 'vi',
      segments: [seg(0), seg(1, { dirty: true, needs: true }), seg(2, { stale: true, needs: true })],
      dirty_count: 1, needs_count: 2,
    });
    retranslateDirty.mockResolvedValue({ job_id: 'j' });
    const onClose = vi.fn();
    wrap(<SegmentDrilldownModal bookId="b" target={{ chapterId: 'ch', lang: 'vi', title: 'Ch 1' }} onClose={onClose} />);

    await waitFor(() => expect(screen.getByText('segments.status_dirty')).toBeTruthy());
    expect(screen.getByText('segments.status_stale')).toBeTruthy();
    expect(screen.getByText('segments.status_clean')).toBeTruthy();

    const btn = screen.getByText('segments.retranslate_changed:2').closest('button') as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
    fireEvent.click(btn);
    await waitFor(() => expect(retranslateDirty).toHaveBeenCalledWith('tok', 'ch', 'vi'));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('S2: surfaces a re-translate failure instead of swallowing it', async () => {
    getSegmentStatus.mockResolvedValue({
      chapter_id: 'ch', target_language: 'vi',
      segments: [seg(0, { dirty: true, needs: true })], dirty_count: 1, needs_count: 1,
    });
    retranslateDirty.mockRejectedValue(new Error('503 boom'));
    wrap(<SegmentDrilldownModal bookId="b" target={{ chapterId: 'ch', lang: 'vi' }} onClose={() => {}} />);
    const btn = (await screen.findByText('segments.retranslate_changed:1')).closest('button') as HTMLButtonElement;
    fireEvent.click(btn);
    expect(await screen.findByTestId('segment-retranslate-error')).toBeInTheDocument();
  });

  it('disables re-translate when nothing needs work', async () => {
    getSegmentStatus.mockResolvedValue({
      chapter_id: 'ch', target_language: 'vi', segments: [seg(0)], dirty_count: 0, needs_count: 0,
    });
    wrap(<SegmentDrilldownModal bookId="b" target={{ chapterId: 'ch', lang: 'vi' }} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText('segments.status_clean')).toBeTruthy());
    const btn = screen.getByText('segments.retranslate_changed:0').closest('button') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(retranslateDirty).not.toHaveBeenCalled();
  });
});
