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

const useEntityDetailMock = vi.fn();
vi.mock('../../hooks/useEntityDetail', () => ({
  useEntityDetail: () => useEntityDetailMock(),
}));

const unlockEntityMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      unlockEntity: (...args: unknown[]) => unlockEntityMock(...args),
    },
  };
});

// Stub the peer dialogs so we don't drag in FormDialog + mutation
// infrastructure they bring with them. EntityDetailPanel just passes
// the entity prop into these; they're irrelevant to the unlock CTA.
vi.mock('../EntityEditDialog', () => ({
  EntityEditDialog: () => <div data-testid="entity-edit-dialog-stub" />,
}));
vi.mock('../EntityMergeDialog', () => ({
  EntityMergeDialog: () => <div data-testid="entity-merge-dialog-stub" />,
}));

import { EntityDetailPanel } from '../EntityDetailPanel';

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const ENTITY = {
  id: 'ent-1',
  user_id: 'u1',
  project_id: 'p-1',
  name: 'Kai',
  canonical_name: 'kai',
  kind: 'character',
  aliases: ['Kai', 'Master Kai'],
  canonical_version: 1,
  source_types: ['chat_turn'],
  confidence: 0.9,
  glossary_entity_id: null,
  anchor_score: 0,
  archived_at: null,
  archive_reason: null,
  evidence_count: 0,
  mention_count: 3,
  user_edited: false,
  version: 5,
  created_at: null,
  updated_at: null,
};

function setDetail(entityOverrides: Partial<typeof ENTITY> = {}) {
  useEntityDetailMock.mockReturnValue({
    detail: {
      entity: { ...ENTITY, ...entityOverrides },
      relations: [],
      relations_truncated: false,
      total_relations: 0,
    },
    isLoading: false,
    error: null,
  });
}

describe('EntityDetailPanel — C9 unlock CTA', () => {
  beforeEach(() => {
    unlockEntityMock.mockReset();
    toastMocks.success.mockReset();
    toastMocks.error.mockReset();
    useEntityDetailMock.mockReset();
    // jsdom stubs window.confirm to return undefined → falsy; we need
    // the CTA to proceed when the user "confirms" in tests.
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('hides the unlock section when user_edited=false', () => {
    setDetail({ user_edited: false });
    render(
      <EntityDetailPanel open={true} onOpenChange={vi.fn()} entityId="ent-1" />,
      { wrapper: Wrapper },
    );
    expect(
      screen.queryByTestId('entity-detail-unlock-section'),
    ).not.toBeInTheDocument();
  });

  it('shows the unlock section when user_edited=true', () => {
    setDetail({ user_edited: true });
    render(
      <EntityDetailPanel open={true} onOpenChange={vi.fn()} entityId="ent-1" />,
      { wrapper: Wrapper },
    );
    expect(
      screen.getByTestId('entity-detail-unlock-section'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('entity-detail-unlock')).toBeInTheDocument();
  });

  it('clicking Unlock fires the mutation + toasts success', async () => {
    setDetail({ user_edited: true });
    unlockEntityMock.mockResolvedValue({ ...ENTITY, user_edited: false, version: 6 });
    render(
      <EntityDetailPanel open={true} onOpenChange={vi.fn()} entityId="ent-1" />,
      { wrapper: Wrapper },
    );
    fireEvent.click(screen.getByTestId('entity-detail-unlock'));
    await waitFor(() => {
      expect(unlockEntityMock).toHaveBeenCalledWith('ent-1', 'tok');
    });
    await waitFor(() => {
      expect(toastMocks.success).toHaveBeenCalledTimes(1);
    });
  });

  it('does not fire mutation when the user cancels the confirm', () => {
    setDetail({ user_edited: true });
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(
      <EntityDetailPanel open={true} onOpenChange={vi.fn()} entityId="ent-1" />,
      { wrapper: Wrapper },
    );
    fireEvent.click(screen.getByTestId('entity-detail-unlock'));
    expect(unlockEntityMock).not.toHaveBeenCalled();
  });
});
