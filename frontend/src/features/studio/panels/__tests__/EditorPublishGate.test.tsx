// #16 Phase 1 task 1.4 — proves the ported Publish Gate actually blocks/warns when wired into
// Studio's shape (bookId/chapterId/draftVersion/dirty props, no ChapterEditorPage around it).
// `useChapterPublishGate`/`publishGateMessages`/`PublishControl`/`usePublishChapter` are NOT
// mocked (DOCK-2 — they're reused as-is, already unit-tested by their own suites); only the
// network boundary (compositionApi, booksApi, sonner) is mocked, so this test exercises the REAL
// gate-composition logic through the new adapter, not a stubbed shortcut.
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
// F2 — the gate flashes the flywheel on publish; stub the host so the test doesn't need the provider.
const openPanel = vi.fn();
vi.mock('../../host/StudioHostProvider', () => ({ useStudioHost: () => ({ openPanel }) }));

const h = vi.hoisted(() => ({
  getChapter: vi.fn(),
  publishChapter: vi.fn(),
  unpublishChapter: vi.fn(),
  resolveWork: vi.fn(),
  publishGate: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock('@/features/books/api', () => ({
  booksApi: {
    getChapter: (...a: unknown[]) => h.getChapter(...a),
    publishChapter: (...a: unknown[]) => h.publishChapter(...a),
    unpublishChapter: (...a: unknown[]) => h.unpublishChapter(...a),
  },
}));
vi.mock('@/features/composition/api', () => ({
  compositionApi: {
    resolveWork: (...a: unknown[]) => h.resolveWork(...a),
    publishGate: (...a: unknown[]) => h.publishGate(...a),
  },
}));
vi.mock('sonner', () => ({ toast: { success: (m: string) => h.toastSuccess(m), error: (m: string) => h.toastError(m) } }));

import { EditorPublishGate } from '../EditorPublishGate';

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const renderGate = (over: Partial<{ bookId: string; chapterId: string; draftVersion: number; dirty: boolean }> = {}) =>
  render(
    <EditorPublishGate bookId="b1" chapterId="c1" draftVersion={4} dirty={false} {...over} />,
    { wrapper: Wrapper },
  );

beforeEach(() => {
  Object.values(h).forEach((fn) => fn.mockReset());
  h.getChapter.mockResolvedValue({ chapter_id: 'c1', editorial_status: 'draft' });
});

describe('EditorPublishGate (Studio wiring — #16 1.4)', () => {
  it('no composition Work → ungated: Publish enabled once editorial_status resolves', async () => {
    h.resolveWork.mockResolvedValue({ status: 'none', work: null, candidates: [] });
    renderGate();
    const btn = await screen.findByText('publish.publish');
    await waitFor(() => expect((btn.closest('button') as HTMLButtonElement).disabled).toBe(false));
    expect(h.publishGate).not.toHaveBeenCalled();
  });

  it('real gate blocks: Work + unfinished scenes → Publish disabled with a reason tooltip', async () => {
    h.resolveWork.mockResolvedValue({ status: 'found', work: { project_id: 'p1' }, candidates: [] });
    h.publishGate.mockResolvedValue({ chapter_id: 'c1', scenes_total: 3, scenes_done: 1, can_publish: false });
    renderGate();
    const btn = await screen.findByText('publish.publish');
    await waitFor(() => expect((btn.closest('button') as HTMLButtonElement).disabled).toBe(true));
    expect((btn.closest('button') as HTMLButtonElement).title).toContain('publish.gate_pending');
    expect(h.publishGate).toHaveBeenCalledWith('p1', 'c1', 'tok');
  });

  it('canon-unchecked (non-blocking) surfaces a warning even though Publish stays enabled', async () => {
    h.resolveWork.mockResolvedValue({ status: 'found', work: { project_id: 'p1' }, candidates: [] });
    h.publishGate.mockResolvedValue({
      chapter_id: 'c1', scenes_total: 2, scenes_done: 2, can_publish: true, canon_unchecked_scenes: 2,
    });
    renderGate();
    const warn = await screen.findByTestId('studio-publish-canon-unchecked');
    expect(warn.textContent).toContain('publish.gate_unchecked');
    const btn = screen.getByText('publish.publish').closest('button') as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });

  it("Studio's dirty flag (unit.isDirty) disables Publish regardless of the gate", async () => {
    h.resolveWork.mockResolvedValue({ status: 'none', work: null, candidates: [] });
    renderGate({ dirty: true });
    const btn = await screen.findByText('publish.publish');
    expect((btn.closest('button') as HTMLButtonElement).disabled).toBe(true);
  });

  it('publish success refetches ONLY editorial_status (light refetch, CM-FE contract)', async () => {
    h.resolveWork.mockResolvedValue({ status: 'none', work: null, candidates: [] });
    h.publishChapter.mockResolvedValue({});
    renderGate();
    const btn = await screen.findByText('publish.publish');
    await waitFor(() => expect((btn.closest('button') as HTMLButtonElement).disabled).toBe(false));
    h.getChapter.mockResolvedValue({ chapter_id: 'c1', editorial_status: 'published' });
    fireEvent.click(btn);
    await waitFor(() => expect(h.publishChapter).toHaveBeenCalledWith('tok', 'b1', 'c1', 4));
    await screen.findByText('publish.republish'); // badge/label flipped after the refetch
    expect(h.getChapter).toHaveBeenCalledTimes(2); // initial load + post-publish invalidation
    // F2 — a publish (pre-change status was 'draft') flashes the flywheel in the background (no focus steal).
    expect(openPanel).toHaveBeenCalledWith('flywheel', { focus: false });
  });
});
