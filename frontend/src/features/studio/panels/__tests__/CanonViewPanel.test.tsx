import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
let activeChapterId: string | null = null;
vi.mock('../../host/StudioHostProvider', () => ({
  useStudioHost: () => ({ bookId: 'book-1' }),
  useStudioBusSelector: (sel: (s: { activeChapterId: string | null }) => unknown) => sel({ activeChapterId }),
}));
vi.mock('../useStudioPanel', () => ({ useStudioPanel: () => undefined }));
vi.mock('@/features/books/api', () => ({
  booksApi: { listChapters: vi.fn().mockResolvedValue({ items: [{ chapter_id: 'ch-1', sort_order: 4 }] }) },
}));
// The leaf is exercised by its own tests; here we assert the wrapper wires focus → leaf.
vi.mock('@/features/composition/components/CanonAtChapterPanel', () => ({
  CanonAtChapterPanel: (p: { chapterId: string | null; chapterIndex: number | null; enabled: boolean }) => (
    <div data-testid="canon-leaf" data-chapter={p.chapterId ?? ''} data-index={p.chapterIndex ?? ''} data-enabled={String(p.enabled)} />
  ),
}));

import { CanonViewPanel } from '../CanonViewPanel';

const props = { api: {} } as never;
const renderPanel = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <CanonViewPanel {...props} />
    </QueryClientProvider>,
  );

describe('CanonViewPanel', () => {
  it('mounts the leaf disabled with no active chapter', () => {
    activeChapterId = null;
    renderPanel();
    const leaf = screen.getByTestId('canon-leaf');
    expect(leaf.getAttribute('data-enabled')).toBe('false');
    expect(leaf.getAttribute('data-chapter')).toBe('');
  });

  it('passes the active chapter to the leaf (enabled)', () => {
    activeChapterId = 'ch-1';
    renderPanel();
    const leaf = screen.getByTestId('canon-leaf');
    expect(leaf.getAttribute('data-enabled')).toBe('true');
    expect(leaf.getAttribute('data-chapter')).toBe('ch-1');
  });
});
