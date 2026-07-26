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

const createEntityMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      createEntity: (...args: unknown[]) => createEntityMock(...args),
    },
  };
});

import { CreateEntityDialog } from '../CreateEntityDialog';
import { AUTHORABLE_ENTITY_KINDS } from '../../lib/entityKinds';

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const FRESH = {
  id: 'ent-new',
  user_id: 'u1',
  project_id: 'p1',
  name: 'Kai',
  canonical_name: 'kai',
  kind: 'character',
  aliases: ['Kai'],
  canonical_version: 1,
  source_types: ['manual'],
  confidence: 1.0,
  glossary_entity_id: null,
  anchor_score: 0,
  archived_at: null,
  archive_reason: null,
  evidence_count: 0,
  mention_count: 0,
  user_edited: false,
  version: 1,
  created_at: null,
  updated_at: null,
};

describe('CreateEntityDialog', () => {
  beforeEach(() => {
    createEntityMock.mockReset();
    toastMocks.success.mockReset();
    toastMocks.error.mockReset();
    toastMocks.info.mockReset();
  });

  it('renders a closed-set kind radio-grid (exactly the 5 authorable kinds)', () => {
    render(
      <CreateEntityDialog open onOpenChange={vi.fn()} projectId="p1" />,
      { wrapper: Wrapper },
    );
    for (const k of AUTHORABLE_ENTITY_KINDS) {
      expect(screen.getByTestId(`entity-create-kind-${k}`)).toBeTruthy();
    }
    // No free-string kind input exists.
    expect(screen.queryByTestId('entity-create-kind-input')).toBeNull();
  });

  it('posts {project_id, name, kind} with the selected kind and toasts success on a fresh node', async () => {
    createEntityMock.mockResolvedValue(FRESH);
    const onOpenChange = vi.fn();
    render(
      <CreateEntityDialog open onOpenChange={onOpenChange} projectId="p1" />,
      { wrapper: Wrapper },
    );
    fireEvent.change(screen.getByTestId('entity-create-name'), {
      target: { value: '  Kai  ' },
    });
    fireEvent.click(screen.getByTestId('entity-create-kind-item'));
    fireEvent.click(screen.getByTestId('entity-create-confirm'));
    await waitFor(() => {
      expect(createEntityMock).toHaveBeenCalledWith(
        { project_id: 'p1', name: 'Kai', kind: 'item' },
        'tok',
      );
    });
    await waitFor(() => {
      expect(toastMocks.success).toHaveBeenCalledTimes(1);
    });
    // OQ-2: a fresh (0-mention) node is a real "created", not a dedup lie.
    expect(toastMocks.info).not.toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('OQ-2: a dedup hit (existing node, mentions>0) toasts INFO, not a "created" success', async () => {
    createEntityMock.mockResolvedValue({ ...FRESH, mention_count: 12 });
    render(
      <CreateEntityDialog open onOpenChange={vi.fn()} projectId="p1" />,
      { wrapper: Wrapper },
    );
    fireEvent.change(screen.getByTestId('entity-create-name'), {
      target: { value: 'Kai' },
    });
    fireEvent.click(screen.getByTestId('entity-create-confirm'));
    await waitFor(() => {
      expect(toastMocks.info).toHaveBeenCalledTimes(1);
    });
    expect(toastMocks.success).not.toHaveBeenCalled();
  });

  it('does not submit a blank name', () => {
    render(
      <CreateEntityDialog open onOpenChange={vi.fn()} projectId="p1" />,
      { wrapper: Wrapper },
    );
    fireEvent.click(screen.getByTestId('entity-create-confirm'));
    expect(createEntityMock).not.toHaveBeenCalled();
  });
});
