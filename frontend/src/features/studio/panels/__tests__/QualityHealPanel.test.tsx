// Studio `quality-heal` — PORT of PolishPanel behind QualityWorkGate with a chapter picker + a
// SERVER-SIDE apply seam (patchDraft with the Polish-run draft_version as OCC). Tests: registers
// openable; picking a chapter mounts PolishPanel; Apply writes the draft with expected_draft_version
// (the E1 stale guard); a 412 surfaces the stale toast (never a silent overwrite); no-work → CTA.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { IDockviewPanelProps } from 'dockview-react';
import type { ReactNode } from 'react';
import { StudioHostProvider, useStudioHost, type StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const useWorkResolution = vi.fn();
vi.mock('@/features/composition/hooks/useWork', () => ({
  useWorkResolution: (b: string, t: string | null) => useWorkResolution(b, t),
  useCreateWork: () => ({ mutateAsync: vi.fn().mockResolvedValue({ project_id: 'proj-new' }), isPending: false }),
  usePendingWorkResolver: () => ({ state: 'idle', start: vi.fn(), retry: vi.fn() }),
}));
vi.mock('@/features/composition/hooks/useActiveWork', () => ({ useActiveWorkId: () => ({ data: undefined }) }));

const listChapters = vi.fn();
const patchDraft = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: {
    listChapters: (...a: unknown[]) => listChapters(...a),
    patchDraft: (...a: unknown[]) => patchDraft(...a),
  },
}));
vi.mock('@/components/model-picker', () => ({
  ModelPicker: ({ onChange }: { onChange: (v: string | null) => void }) => (
    <button data-testid="stub-model" onClick={() => onChange('m1')}>model</button>
  ),
}));
// Stub PolishPanel: expose the onApply seam so the test can fire it with a known draft_version.
vi.mock('@/features/composition/components/PolishPanel', () => ({
  PolishPanel: ({ chapterId, onApply }: { chapterId: string; onApply: (t: string, v: number | null) => void }) => (
    <div data-testid="stub-polish" data-chapter={chapterId}>
      <button data-testid="stub-apply" onClick={() => onApply('healed prose', 7)}>apply</button>
    </div>
  ),
}));

const toastError = vi.fn();
const toastSuccess = vi.fn();
vi.mock('sonner', () => ({ toast: { error: (m: string) => toastError(m), success: (m: string) => toastSuccess(m) } }));

import { QualityHealPanel } from '../QualityHealPanel';

function dockProps() { return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps; }
let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }
function withHost(bookId: string, ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  hostRef = null;
  useWorkResolution.mockReset();
  listChapters.mockReset();
  patchDraft.mockReset();
  toastError.mockReset();
  toastSuccess.mockReset();
  useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'found', work: { project_id: 'p1' } } });
  listChapters.mockResolvedValue({ items: [{ chapter_id: 'ch1', title: 'Ch 1', sort_order: 1 }], total: 1 });
});

describe('QualityHealPanel', () => {
  it('registers with the host as an openable studio tool', () => {
    withHost('b1', <QualityHealPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('quality-heal')).not.toBeNull();
  });

  it('mounts PolishPanel once a chapter is picked', async () => {
    withHost('b1', <QualityHealPanel {...dockProps()} />);
    await waitFor(() => expect(screen.getByRole('option', { name: 'Ch 1' })).toBeInTheDocument());
    fireEvent.change(screen.getByTestId('quality-heal-chapter-picker'), { target: { value: 'ch1' } });
    expect(screen.getByTestId('stub-polish')).toHaveAttribute('data-chapter', 'ch1');
  });

  it('Apply writes the draft with the Polish-run version as OCC (E1 stale guard)', async () => {
    patchDraft.mockResolvedValue(undefined);
    withHost('b1', <QualityHealPanel {...dockProps()} />);
    await waitFor(() => expect(screen.getByRole('option', { name: 'Ch 1' })).toBeInTheDocument());
    fireEvent.change(screen.getByTestId('quality-heal-chapter-picker'), { target: { value: 'ch1' } });
    fireEvent.click(screen.getByTestId('stub-apply'));
    await waitFor(() => expect(patchDraft).toHaveBeenCalled());
    const [, bookId, chapterId, payload] = patchDraft.mock.calls[0];
    expect(bookId).toBe('b1');
    expect(chapterId).toBe('ch1');
    expect(payload.expected_draft_version).toBe(7);
    expect(toastSuccess).toHaveBeenCalled();
  });

  it('a 412 (chapter changed since Polish) surfaces the stale toast — never a silent overwrite', async () => {
    patchDraft.mockRejectedValue(new Error('412 draft version conflict'));
    withHost('b1', <QualityHealPanel {...dockProps()} />);
    await waitFor(() => expect(screen.getByRole('option', { name: 'Ch 1' })).toBeInTheDocument());
    fireEvent.change(screen.getByTestId('quality-heal-chapter-picker'), { target: { value: 'ch1' } });
    fireEvent.click(screen.getByTestId('stub-apply'));
    await waitFor(() => expect(toastError).toHaveBeenCalled());
  });

  it('offers the Set-up-co-writer CTA on a fresh (no-work) book', () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'none', work: null } });
    withHost('b1', <QualityHealPanel {...dockProps()} />);
    expect(screen.getByTestId('quality-heal-no-work')).toBeInTheDocument();
    expect(screen.getByTestId('work-setup-cta')).toBeInTheDocument();
  });
});
