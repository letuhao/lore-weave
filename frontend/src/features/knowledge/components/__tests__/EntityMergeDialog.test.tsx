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

const toastMocks = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: toastMocks }));

const listEntitiesMock = vi.fn();
const mergeEntityIntoMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      listEntities: (...args: unknown[]) => listEntitiesMock(...args),
      mergeEntityInto: (...args: unknown[]) => mergeEntityIntoMock(...args),
    },
  };
});

import { EntityMergeDialog } from '../EntityMergeDialog';

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const SOURCE = {
  id: 'src-id',
  user_id: 'u1',
  project_id: null,
  name: 'Kai',
  canonical_name: 'kai',
  kind: 'character',
  aliases: ['Kai'],
  canonical_version: 1,
  source_types: ['chat_turn'],
  confidence: 0.9,
  archived_at: null,
  archive_reason: null,
  evidence_count: 0,
  mention_count: 5,
  created_at: null,
  updated_at: null,
};

const CANDIDATE = {
  ...SOURCE,
  id: 'target-id',
  name: 'Phoenix',
  canonical_name: 'phoenix',
  aliases: ['Phoenix'],
  mention_count: 10,
};

describe('EntityMergeDialog', () => {
  beforeEach(() => {
    listEntitiesMock.mockReset();
    mergeEntityIntoMock.mockReset();
    toastMocks.success.mockReset();
    toastMocks.error.mockReset();
    listEntitiesMock.mockResolvedValue({
      entities: [SOURCE, CANDIDATE],
      total: 2,
    });
  });

  it('disables confirm until a target is selected', async () => {
    render(
      <EntityMergeDialog open={true} onOpenChange={vi.fn()} source={SOURCE} />,
      { wrapper: Wrapper },
    );
    const confirm = await screen.findByTestId('entity-merge-confirm');
    expect(confirm).toBeDisabled();
  });

  it('searches and filters out the source entity from candidates', async () => {
    render(
      <EntityMergeDialog open={true} onOpenChange={vi.fn()} source={SOURCE} />,
      { wrapper: Wrapper },
    );
    fireEvent.change(screen.getByTestId('entity-merge-search'), {
      target: { value: 'ph' },
    });
    const candidates = await screen.findAllByTestId('entity-merge-candidate');
    // listEntitiesMock returned 2 entities; source filtered out → 1 visible.
    expect(candidates).toHaveLength(1);
    expect(candidates[0].textContent).toContain('Phoenix');
  });

  it('submits merge and toasts success + invokes onMerged on success', async () => {
    mergeEntityIntoMock.mockResolvedValue({
      target: { ...CANDIDATE, name: 'Phoenix' },
    });
    const onMerged = vi.fn();
    const onOpenChange = vi.fn();
    render(
      <EntityMergeDialog
        open={true}
        onOpenChange={onOpenChange}
        source={SOURCE}
        onMerged={onMerged}
      />,
      { wrapper: Wrapper },
    );
    fireEvent.change(screen.getByTestId('entity-merge-search'), {
      target: { value: 'phoenix' },
    });
    const candidates = await screen.findAllByTestId('entity-merge-candidate');
    fireEvent.click(candidates[0]);
    // Selected card renders, confirm enabled.
    await screen.findByTestId('entity-merge-selected');
    fireEvent.click(screen.getByTestId('entity-merge-confirm'));
    await waitFor(() => {
      expect(mergeEntityIntoMock).toHaveBeenCalledWith(
        'src-id',
        'target-id',
        'tok',
      );
    });
    await waitFor(() => {
      expect(toastMocks.success).toHaveBeenCalledTimes(1);
    });
    expect(onMerged).toHaveBeenCalledWith('target-id');
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('toasts glossary-conflict specifically on 409 glossary_conflict', async () => {
    mergeEntityIntoMock.mockRejectedValue(
      Object.assign(new Error('conflict'), {
        status: 409,
        body: {
          detail: { error_code: 'glossary_conflict', message: 'anchors' },
        },
      }),
    );
    render(
      <EntityMergeDialog open={true} onOpenChange={vi.fn()} source={SOURCE} />,
      { wrapper: Wrapper },
    );
    fireEvent.change(screen.getByTestId('entity-merge-search'), {
      target: { value: 'phoenix' },
    });
    const candidates = await screen.findAllByTestId('entity-merge-candidate');
    fireEvent.click(candidates[0]);
    fireEvent.click(screen.getByTestId('entity-merge-confirm'));
    await waitFor(() => {
      expect(toastMocks.error).toHaveBeenCalledTimes(1);
    });
  });
});
