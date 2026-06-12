import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({
  useAuth: () => ({
    accessToken: 'tok',
    user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
  }),
}));

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock('sonner', () => ({ toast: toastMocks }));

const correctMock = vi.fn();
const invalidateMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      correctRelation: (...a: unknown[]) => correctMock(...a),
      invalidateRelation: (...a: unknown[]) => invalidateMock(...a),
    },
  };
});

import { RelationEditDialog } from '../RelationEditDialog';

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const REL = {
  id: 'rel-1', subject_id: 's1', object_id: 'o1', predicate: 'ally_of',
  confidence: 0.8, source_event_ids: [], source_chapter: null,
  valid_from: null, valid_until: null, pending_validation: false,
  created_at: null, updated_at: null,
  subject_name: 'Kai', subject_kind: 'character',
  object_name: 'Phoenix', object_kind: 'character',
};

describe('RelationEditDialog', () => {
  beforeEach(() => {
    correctMock.mockReset();
    invalidateMock.mockReset();
    toastMocks.success.mockReset();
    toastMocks.error.mockReset();
  });

  it('pre-fills the predicate', () => {
    render(<RelationEditDialog open onOpenChange={vi.fn()} relation={REL} />, { wrapper: Wrapper });
    expect((screen.getByTestId('relation-edit-predicate') as HTMLInputElement).value).toBe('ally_of');
  });

  it('correct submits the invalidate-old + recreate payload', async () => {
    correctMock.mockResolvedValue({ ...REL, predicate: 'enemy_of' });
    const onOpenChange = vi.fn();
    render(<RelationEditDialog open onOpenChange={onOpenChange} relation={REL} />, { wrapper: Wrapper });
    fireEvent.change(screen.getByTestId('relation-edit-predicate'), {
      target: { value: 'enemy_of' },
    });
    fireEvent.click(screen.getByTestId('relation-edit-confirm'));
    await waitFor(() => {
      expect(correctMock).toHaveBeenCalledWith(
        { old_relation_id: 'rel-1', subject_id: 's1', predicate: 'enemy_of', object_id: 'o1' },
        'tok',
      );
    });
    await waitFor(() => expect(toastMocks.success).toHaveBeenCalledTimes(1));
  });

  it('closes without calling API when predicate unchanged', async () => {
    const onOpenChange = vi.fn();
    render(<RelationEditDialog open onOpenChange={onOpenChange} relation={REL} />, { wrapper: Wrapper });
    fireEvent.click(screen.getByTestId('relation-edit-confirm'));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(correctMock).not.toHaveBeenCalled();
  });

  it('mark-wrong invalidates after confirm', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    invalidateMock.mockResolvedValue({ ...REL, valid_until: '2026-05-31T00:00:00Z' });
    const onOpenChange = vi.fn();
    render(<RelationEditDialog open onOpenChange={onOpenChange} relation={REL} />, { wrapper: Wrapper });
    fireEvent.click(screen.getByTestId('relation-edit-invalidate'));
    await waitFor(() => expect(invalidateMock).toHaveBeenCalledWith('rel-1', 'tok'));
    await waitFor(() => expect(toastMocks.success).toHaveBeenCalledTimes(1));
    confirmSpy.mockRestore();
  });

  it('mark-wrong does nothing when confirm cancelled', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<RelationEditDialog open onOpenChange={vi.fn()} relation={REL} />, { wrapper: Wrapper });
    fireEvent.click(screen.getByTestId('relation-edit-invalidate'));
    await waitFor(() => expect(confirmSpy).toHaveBeenCalled());
    expect(invalidateMock).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});
