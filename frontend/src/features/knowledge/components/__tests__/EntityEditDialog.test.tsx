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

const updateEntityMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      updateEntity: (...args: unknown[]) => updateEntityMock(...args),
    },
  };
});

import { EntityEditDialog } from '../EntityEditDialog';

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const ENTITY = {
  id: 'ent-1',
  user_id: 'u1',
  project_id: null,
  name: 'Kai',
  canonical_name: 'kai',
  kind: 'character',
  aliases: ['Kai', 'Master Kai'],
  canonical_version: 1,
  source_types: ['chat_turn'],
  confidence: 0.9,
  archived_at: null,
  archive_reason: null,
  evidence_count: 0,
  mention_count: 0,
  created_at: null,
  updated_at: null,
};

describe('EntityEditDialog', () => {
  beforeEach(() => {
    updateEntityMock.mockReset();
    toastMocks.success.mockReset();
    toastMocks.error.mockReset();
  });

  it('pre-fills fields from the entity', () => {
    const onOpenChange = vi.fn();
    render(
      <EntityEditDialog open={true} onOpenChange={onOpenChange} entity={ENTITY} />,
      { wrapper: Wrapper },
    );
    expect((screen.getByTestId('entity-edit-name') as HTMLInputElement).value).toBe(
      'Kai',
    );
    expect(
      (screen.getByTestId('entity-edit-aliases') as HTMLTextAreaElement).value,
    ).toBe('Kai\nMaster Kai');
  });

  it('submits only changed fields and toasts success', async () => {
    updateEntityMock.mockResolvedValue({ ...ENTITY, name: 'Kai the Brave' });
    const onOpenChange = vi.fn();
    render(
      <EntityEditDialog open={true} onOpenChange={onOpenChange} entity={ENTITY} />,
      { wrapper: Wrapper },
    );
    fireEvent.change(screen.getByTestId('entity-edit-name'), {
      target: { value: 'Kai the Brave' },
    });
    fireEvent.click(screen.getByTestId('entity-edit-confirm'));
    await waitFor(() => {
      expect(updateEntityMock).toHaveBeenCalledWith(
        'ent-1',
        { name: 'Kai the Brave', kind: undefined, aliases: undefined },
        'tok',
      );
    });
    await waitFor(() => {
      expect(toastMocks.success).toHaveBeenCalledTimes(1);
    });
  });

  it('deduplicates + trims aliases from the textarea', async () => {
    updateEntityMock.mockResolvedValue(ENTITY);
    const onOpenChange = vi.fn();
    render(
      <EntityEditDialog open={true} onOpenChange={onOpenChange} entity={ENTITY} />,
      { wrapper: Wrapper },
    );
    fireEvent.change(screen.getByTestId('entity-edit-aliases'), {
      target: { value: '  Kai  \n\nKai\nK.\n' },
    });
    fireEvent.click(screen.getByTestId('entity-edit-confirm'));
    await waitFor(() => {
      expect(updateEntityMock).toHaveBeenCalledTimes(1);
    });
    const [, payload] = updateEntityMock.mock.calls[0];
    expect(payload.aliases).toEqual(['Kai', 'K.']);
  });

  it('closes without calling API when nothing changed', async () => {
    const onOpenChange = vi.fn();
    render(
      <EntityEditDialog open={true} onOpenChange={onOpenChange} entity={ENTITY} />,
      { wrapper: Wrapper },
    );
    fireEvent.click(screen.getByTestId('entity-edit-confirm'));
    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
    expect(updateEntityMock).not.toHaveBeenCalled();
  });

  it('toasts error on update failure', async () => {
    updateEntityMock.mockRejectedValue(new Error('boom'));
    const onOpenChange = vi.fn();
    render(
      <EntityEditDialog open={true} onOpenChange={onOpenChange} entity={ENTITY} />,
      { wrapper: Wrapper },
    );
    fireEvent.change(screen.getByTestId('entity-edit-name'), {
      target: { value: 'Changed' },
    });
    fireEvent.click(screen.getByTestId('entity-edit-confirm'));
    await waitFor(() => {
      expect(toastMocks.error).toHaveBeenCalledTimes(1);
    });
  });
});
