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

const createRelationMock = vi.fn();
const listEntitiesMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      createRelation: (...args: unknown[]) => createRelationMock(...args),
      listEntities: (...args: unknown[]) => listEntitiesMock(...args),
    },
  };
});

import { CreateRelationDialog } from '../CreateRelationDialog';
import { RELATION_PREDICATES } from '../../lib/entityKinds';

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function renderDialog() {
  return render(
    <CreateRelationDialog
      open
      onOpenChange={vi.fn()}
      projectId="p1"
      subjectId="s1"
      subjectName="李慕白"
    />,
    { wrapper: Wrapper },
  );
}

describe('CreateRelationDialog', () => {
  beforeEach(() => {
    createRelationMock.mockReset();
    listEntitiesMock.mockReset();
    listEntitiesMock.mockResolvedValue({ entities: [], total: 0 });
    toastMocks.success.mockReset();
    toastMocks.error.mockReset();
  });

  it('offers the closed-set predicate enum (never a free input)', () => {
    renderDialog();
    const sel = screen.getByTestId('relation-create-predicate') as HTMLSelectElement;
    const opts = Array.from(sel.options).map((o) => o.value);
    expect(opts).toEqual([...RELATION_PREDICATES]);
    expect(sel.tagName).toBe('SELECT');
  });

  it('seeds the subject and disables submit until an object is picked', () => {
    renderDialog();
    expect(screen.getByTestId('relation-create-subject').textContent).toBe('李慕白');
    expect(
      (screen.getByTestId('relation-create-confirm') as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it('surfaces a 409 (endpoint not yours) with the specific toast, no fake success', async () => {
    listEntitiesMock.mockResolvedValue({
      entities: [{ id: 'o1', name: 'Hàn Lập', kind: 'character' }],
      total: 1,
    });
    createRelationMock.mockRejectedValue(
      Object.assign(new Error('conflict'), { status: 409 }),
    );
    renderDialog();
    fireEvent.change(screen.getByTestId('relation-create-object-search'), {
      target: { value: 'Hàn' },
    });
    await waitFor(() => {
      expect(screen.getByTestId('relation-create-object-o1')).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId('relation-create-object-o1'));
    fireEvent.click(screen.getByTestId('relation-create-confirm'));
    await waitFor(() => {
      expect(toastMocks.error).toHaveBeenCalledWith('relations.create.notYours');
    });
    expect(toastMocks.success).not.toHaveBeenCalled();
  });

  it('surfaces a 422 self-loop with the specific toast', async () => {
    listEntitiesMock.mockResolvedValue({
      entities: [{ id: 'o1', name: 'Hàn Lập', kind: 'character' }],
      total: 1,
    });
    createRelationMock.mockRejectedValue(
      Object.assign(new Error('self loop'), { status: 422 }),
    );
    renderDialog();
    fireEvent.change(screen.getByTestId('relation-create-object-search'), {
      target: { value: 'Hàn' },
    });
    await waitFor(() => {
      expect(screen.getByTestId('relation-create-object-o1')).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId('relation-create-object-o1'));
    fireEvent.click(screen.getByTestId('relation-create-confirm'));
    await waitFor(() => {
      expect(toastMocks.error).toHaveBeenCalledWith('relations.create.selfLoop');
    });
  });
});
