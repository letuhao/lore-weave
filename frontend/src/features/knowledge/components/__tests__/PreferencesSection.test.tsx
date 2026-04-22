import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { Entity } from '../../api';

vi.mock('@/auth', () => ({
  useAuth: () => ({
    accessToken: 'tok-test',
    user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
  }),
}));

const archiveMyEntityMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      archiveMyEntity: (...args: unknown[]) => archiveMyEntityMock(...args),
    },
  };
});

const toastSuccessMock = vi.fn();
const toastErrorMock = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccessMock(...a),
    error: (...a: unknown[]) => toastErrorMock(...a),
  },
}));

const useUserEntitiesMock = vi.fn();
vi.mock('../../hooks/useUserEntities', () => ({
  useUserEntities: () => useUserEntitiesMock(),
}));

import { PreferencesSection } from '../PreferencesSection';

function entity(overrides: Partial<Entity> & { id: string; name: string }): Entity {
  return {
    user_id: 'u1',
    project_id: null,
    canonical_name: overrides.name.toLowerCase(),
    kind: 'preference',
    aliases: [overrides.name],
    canonical_version: 1,
    source_types: ['chat_turn'],
    confidence: 0.9,
    glossary_entity_id: null,
    anchor_score: 0,
    archived_at: null,
    archive_reason: null,
    evidence_count: 1,
    mention_count: 1,
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function setHookState(overrides: {
  entities?: Entity[];
  isLoading?: boolean;
  error?: Error | null;
}) {
  useUserEntitiesMock.mockReturnValue({
    entities: overrides.entities ?? [],
    isLoading: overrides.isLoading ?? false,
    error: overrides.error ?? null,
  });
}

function renderSection() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    ...render(
      <QueryClientProvider client={qc}>
        <PreferencesSection />
      </QueryClientProvider>,
    ),
    qc,
  };
}

describe('PreferencesSection', () => {
  beforeEach(() => {
    useUserEntitiesMock.mockReset();
    archiveMyEntityMock.mockReset();
    toastSuccessMock.mockReset();
    toastErrorMock.mockReset();
  });

  it('renders loading state while fetching', () => {
    setHookState({ isLoading: true });
    renderSection();
    expect(screen.getByTestId('preferences-loading')).toBeInTheDocument();
  });

  it('renders error message when the hook errors', () => {
    setHookState({ error: new Error('network down') });
    renderSection();
    expect(screen.getByTestId('preferences-error')).toHaveTextContent('network down');
  });

  it('renders empty state when no entities exist', () => {
    setHookState({ entities: [] });
    renderSection();
    expect(screen.getByTestId('preferences-empty')).toBeInTheDocument();
  });

  it('renders one row per entity with kind badge and name', () => {
    setHookState({
      entities: [
        entity({ id: 'e1', name: 'Coffee drinker', kind: 'preference' }),
        entity({ id: 'e2', name: 'Vietnamese writer', kind: 'preference' }),
      ],
    });
    renderSection();
    const rows = screen.getAllByTestId('preferences-row');
    expect(rows).toHaveLength(2);
    expect(rows[0].getAttribute('data-entity-id')).toBe('e1');
    expect(screen.getByText('Coffee drinker')).toBeInTheDocument();
    expect(screen.getByText('Vietnamese writer')).toBeInTheDocument();
  });

  it('opens confirm dialog on delete click and archives + invalidates on confirm', async () => {
    archiveMyEntityMock.mockResolvedValue(undefined);
    setHookState({
      entities: [entity({ id: 'e1', name: 'Coffee drinker' })],
    });
    const { qc } = renderSection();
    const spy = vi.spyOn(qc, 'invalidateQueries');

    // Trash-can button opens the dialog (no archive fired yet).
    fireEvent.click(screen.getByTestId('preferences-delete'));
    expect(archiveMyEntityMock).not.toHaveBeenCalled();

    // Click confirm in the dialog → DELETE fires.
    fireEvent.click(screen.getByTestId('preferences-confirm-delete'));
    await waitFor(() => {
      expect(archiveMyEntityMock).toHaveBeenCalledWith('e1', 'tok-test');
    });
    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith({
        queryKey: ['knowledge-user-entities', 'u1', 'global'],
      });
    });
    await waitFor(() => {
      expect(toastSuccessMock).toHaveBeenCalled();
    });
  });

  it('toasts on delete failure and keeps dialog open', async () => {
    archiveMyEntityMock.mockRejectedValue(new Error('server error'));
    setHookState({
      entities: [entity({ id: 'e1', name: 'Coffee drinker' })],
    });
    renderSection();
    fireEvent.click(screen.getByTestId('preferences-delete'));
    fireEvent.click(screen.getByTestId('preferences-confirm-delete'));
    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalled();
    });
    // Confirm button still in the DOM — dialog didn't close.
    expect(screen.getByTestId('preferences-confirm-delete')).toBeInTheDocument();
  });
});
