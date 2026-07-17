import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

// S-05 Part B — the triage panel drives the COMPLETE-but-uncalled public routes.
// We mock the api layer and use the REAL hook + component so the test proves the
// panel actually calls listTriage/resolveTriage (operability), not just renders.

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }),
}));

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock('sonner', () => ({ toast: toastMocks }));

const listTriageMock = vi.fn();
const resolveTriageMock = vi.fn();
const listTriageItemsMock = vi.fn();
const dismissTriageItemMock = vi.fn();
vi.mock('../../api/ontology', () => ({
  ontologyApi: {
    listTriage: (...a: unknown[]) => listTriageMock(...a),
    resolveTriage: (...a: unknown[]) => resolveTriageMock(...a),
    listTriageItems: (...a: unknown[]) => listTriageItemsMock(...a),
    dismissTriageItem: (...a: unknown[]) => dismissTriageItemMock(...a),
  },
}));

// S-05b — stub the entity-picker dialog: expose a "pick" button so the test can
// drive re_target through the picker (the dialog itself is tested separately with
// useEntities mocked). Renders only when open.
vi.mock('../TriageRetargetDialog', () => ({
  TriageRetargetDialog: ({
    open,
    onPick,
  }: {
    open: boolean;
    onPick: (id: string) => void;
  }) =>
    open ? (
      <button data-testid="retarget-stub-pick" onClick={() => onPick('ent-99')}>
        pick
      </button>
    ) : null,
}));

// S-05b — stub the map code-select dialog (tested separately with useResolvedSchema
// mocked). Exposes a "pick code" + "keep detected" button.
vi.mock('../TriageMapDialog', () => ({
  TriageMapDialog: ({
    open,
    onPick,
  }: {
    open: boolean;
    onPick: (code: string | null) => void;
  }) =>
    open ? (
      <div>
        <button data-testid="map-stub-pick" onClick={() => onPick('rules_over')}>
          pick
        </button>
        <button data-testid="map-stub-keep" onClick={() => onPick(null)}>
          keep
        </button>
      </div>
    ) : null,
}));

import { TriageQueue } from '../TriageQueue';

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const GROUP_EDGE_MISMATCH = {
  signature: 'sig-1',
  item_type: 'edge_kind_mismatch' as const,
  count: 3,
  status: 'pending' as const,
  sample_payload: { predicate: 'rules_over' },
  // includes a value the FE can't drive (place_edge) — must NOT render.
  suggested_actions: ['re_target', 'widen_target_kinds', 'drop_edge', 'place_edge'],
};
const GROUP_UNKNOWN_KIND = {
  signature: 'sig-2',
  item_type: 'unknown_node_kind' as const,
  count: 1,
  status: 'pending' as const,
  sample_payload: { proposed_kind: 'deity' },
  suggested_actions: ['promote_to_glossary_kind', 'demote_to_attribute', 'map', 'dismiss'],
};

describe('TriageQueue', () => {
  beforeEach(() => {
    listTriageMock.mockReset();
    resolveTriageMock.mockReset();
    listTriageItemsMock.mockReset();
    dismissTriageItemMock.mockReset();
    toastMocks.success.mockReset();
    toastMocks.error.mockReset();
    toastMocks.info.mockReset();
  });

  it('renders the empty state when the queue is clear', async () => {
    listTriageMock.mockResolvedValue({ groups: [] });
    render(<TriageQueue projectId="p-1" />, { wrapper: Wrapper });
    await waitFor(() =>
      expect(screen.getByTestId('kg-triage-empty')).toBeInTheDocument(),
    );
  });

  it('renders ONLY the resolve-completing actions (no dead place_edge, no silent-partial schema action)', async () => {
    listTriageMock.mockResolvedValue({ groups: [GROUP_EDGE_MISMATCH] });
    render(<TriageQueue projectId="p-1" />, { wrapper: Wrapper });
    await waitFor(() =>
      expect(screen.getByTestId('kg-triage-group')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('kg-triage-action-re_target')).toBeInTheDocument();
    expect(screen.getByTestId('kg-triage-action-drop_edge')).toBeInTheDocument();
    // place_edge = confirm-token flow, not a resolve action → never a button.
    expect(screen.queryByTestId('kg-triage-action-place_edge')).not.toBeInTheDocument();
    // widen_target_kinds = schema-mutating: resolve only records intent (no write),
    // so offering it would vanish the item without changing the schema. Excluded.
    expect(screen.queryByTestId('kg-triage-action-widen_target_kinds')).not.toBeInTheDocument();
  });

  it('a no-param action resolves the signature + toasts', async () => {
    listTriageMock.mockResolvedValue({ groups: [GROUP_EDGE_MISMATCH] });
    resolveTriageMock.mockResolvedValue({ status: 'resolved', affected: 3 });
    render(<TriageQueue projectId="p-1" />, { wrapper: Wrapper });
    await waitFor(() => screen.getByTestId('kg-triage-action-drop_edge'));
    fireEvent.click(screen.getByTestId('kg-triage-action-drop_edge'));
    await waitFor(() => expect(resolveTriageMock).toHaveBeenCalledTimes(1));
    expect(resolveTriageMock).toHaveBeenCalledWith(
      'p-1', 'sig-1', { action: 'drop_edge', params: {} }, 'tok',
    );
    await waitFor(() => expect(toastMocks.success).toHaveBeenCalled());
  });

  it('re_target opens the entity PICKER (no UUID prompt) and resolves with the picked id', async () => {
    const promptSpy = vi.spyOn(window, 'prompt');
    listTriageMock.mockResolvedValue({ groups: [GROUP_EDGE_MISMATCH] });
    resolveTriageMock.mockResolvedValue({ status: 'resolved', affected: 1 });
    render(<TriageQueue projectId="p-1" />, { wrapper: Wrapper });
    await waitFor(() => screen.getByTestId('kg-triage-action-re_target'));
    fireEvent.click(screen.getByTestId('kg-triage-action-re_target'));
    // NO window.prompt — the picker opens instead
    expect(promptSpy).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByTestId('retarget-stub-pick'));
    await waitFor(() =>
      expect(resolveTriageMock).toHaveBeenCalledWith(
        'p-1', 'sig-1',
        { action: 're_target', params: { target_entity_id: 'ent-99' } },
        'tok',
      ),
    );
    promptSpy.mockRestore();
  });

  it('re_target fires nothing until the user actually picks (cancel = no-op)', async () => {
    listTriageMock.mockResolvedValue({ groups: [GROUP_EDGE_MISMATCH] });
    render(<TriageQueue projectId="p-1" />, { wrapper: Wrapper });
    await waitFor(() => screen.getByTestId('kg-triage-action-re_target'));
    fireEvent.click(screen.getByTestId('kg-triage-action-re_target'));
    // picker opened but nothing picked yet
    await screen.findByTestId('retarget-stub-pick');
    expect(resolveTriageMock).not.toHaveBeenCalled();
  });

  it('glossary handoff (422 body) deep-links via onGlossaryHandoff', async () => {
    const onGlossaryHandoff = vi.fn();
    listTriageMock.mockResolvedValue({ groups: [GROUP_UNKNOWN_KIND] });
    // the handoff comes back as a 422 with the needs_glossary body
    resolveTriageMock.mockRejectedValue(
      Object.assign(new Error('unprocessable'), {
        status: 422,
        body: { status: 'pending_glossary', needs_glossary: { book_id: 'b-1', kinds: ['deity'] } },
      }),
    );
    render(
      <TriageQueue projectId="p-1" bookId="b-1" onGlossaryHandoff={onGlossaryHandoff} />,
      { wrapper: Wrapper },
    );
    await waitFor(() => screen.getByTestId('kg-triage-action-promote_to_glossary_kind'));
    fireEvent.click(screen.getByTestId('kg-triage-action-promote_to_glossary_kind'));
    await waitFor(() =>
      expect(onGlossaryHandoff).toHaveBeenCalledWith({ book_id: 'b-1', kinds: ['deity'] }),
    );
  });

  it('map opens the code SELECT (no raw-code prompt); picking a code resolves with map_to', async () => {
    const promptSpy = vi.spyOn(window, 'prompt');
    listTriageMock.mockResolvedValue({ groups: [GROUP_UNKNOWN_KIND] }); // has 'map'
    resolveTriageMock.mockResolvedValue({ status: 'resolved', affected: 1 });
    render(<TriageQueue projectId="p-1" />, { wrapper: Wrapper });
    await waitFor(() => screen.getByTestId('kg-triage-action-map'));
    fireEvent.click(screen.getByTestId('kg-triage-action-map'));
    expect(promptSpy).not.toHaveBeenCalled(); // picker, not prompt
    fireEvent.click(await screen.findByTestId('map-stub-pick'));
    await waitFor(() =>
      expect(resolveTriageMock).toHaveBeenCalledWith(
        'p-1', 'sig-2', { action: 'map', params: { map_to: 'rules_over' } }, 'tok',
      ),
    );
    promptSpy.mockRestore();
  });

  it('map "keep detected value" resolves with empty params (backend uses the parked value)', async () => {
    listTriageMock.mockResolvedValue({ groups: [GROUP_UNKNOWN_KIND] });
    resolveTriageMock.mockResolvedValue({ status: 'resolved', affected: 1 });
    render(<TriageQueue projectId="p-1" />, { wrapper: Wrapper });
    await waitFor(() => screen.getByTestId('kg-triage-action-map'));
    fireEvent.click(screen.getByTestId('kg-triage-action-map'));
    fireEvent.click(await screen.findByTestId('map-stub-keep'));
    await waitFor(() =>
      expect(resolveTriageMock).toHaveBeenCalledWith(
        'p-1', 'sig-2', { action: 'map', params: {} }, 'tok',
      ),
    );
  });

  it('add_to_schema now renders + writes on confirm (S-05 schema write)', async () => {
    const group = {
      signature: 'edge:rules_over',
      item_type: 'unknown_edge_type' as const,
      count: 2,
      status: 'pending' as const,
      sample_payload: { predicate: 'rules_over' },
      suggested_actions: ['map', 'add_to_schema', 'dismiss'],
    };
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    listTriageMock.mockResolvedValue({ groups: [group] });
    resolveTriageMock.mockResolvedValue({ status: 'resolved', affected: 2, schema_version: 4 });
    render(<TriageQueue projectId="p-1" />, { wrapper: Wrapper });
    await waitFor(() => screen.getByTestId('kg-triage-action-add_to_schema'));
    fireEvent.click(screen.getByTestId('kg-triage-action-add_to_schema'));
    await waitFor(() =>
      expect(resolveTriageMock).toHaveBeenCalledWith(
        'p-1', 'edge:rules_over', { action: 'add_to_schema', params: {} }, 'tok',
      ),
    );
    expect(confirmSpy).toHaveBeenCalled(); // ontology change is confirmed first
    confirmSpy.mockRestore();
  });

  it('add_to_schema does NOT fire when the schema-write confirm is cancelled', async () => {
    const group = {
      signature: 'edge:rules_over',
      item_type: 'unknown_edge_type' as const,
      count: 1,
      status: 'pending' as const,
      sample_payload: { predicate: 'rules_over' },
      suggested_actions: ['add_to_schema', 'dismiss'],
    };
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    listTriageMock.mockResolvedValue({ groups: [group] });
    render(<TriageQueue projectId="p-1" />, { wrapper: Wrapper });
    await waitFor(() => screen.getByTestId('kg-triage-action-add_to_schema'));
    fireEvent.click(screen.getByTestId('kg-triage-action-add_to_schema'));
    await new Promise((r) => setTimeout(r, 20));
    expect(resolveTriageMock).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('expands a multi-item group and dismisses ONE item (per-item, not the group)', async () => {
    listTriageMock.mockResolvedValue({ groups: [GROUP_EDGE_MISMATCH] }); // count: 3
    listTriageItemsMock.mockResolvedValue({
      items: [
        { triage_id: 'ti-1', item_type: 'edge_kind_mismatch', payload: { predicate: 'rules_over' } },
        { triage_id: 'ti-2', item_type: 'edge_kind_mismatch', payload: { predicate: 'reigns' } },
      ],
    });
    dismissTriageItemMock.mockResolvedValue(undefined);
    render(<TriageQueue projectId="p-1" />, { wrapper: Wrapper });
    await waitFor(() => screen.getByTestId('kg-triage-expand'));
    fireEvent.click(screen.getByTestId('kg-triage-expand'));
    await waitFor(() =>
      expect(screen.getAllByTestId('kg-triage-item')).toHaveLength(2),
    );
    fireEvent.click(screen.getAllByTestId('kg-triage-item-dismiss')[0]);
    await waitFor(() =>
      expect(dismissTriageItemMock).toHaveBeenCalledWith('p-1', 'ti-1', 'tok'),
    );
    // per-item dismiss must NOT fire a whole-group resolve
    expect(resolveTriageMock).not.toHaveBeenCalled();
    await waitFor(() => expect(toastMocks.success).toHaveBeenCalled());
  });
});
