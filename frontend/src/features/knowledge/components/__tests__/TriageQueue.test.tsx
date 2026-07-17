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
vi.mock('../../api/ontology', () => ({
  ontologyApi: {
    listTriage: (...a: unknown[]) => listTriageMock(...a),
    resolveTriage: (...a: unknown[]) => resolveTriageMock(...a),
  },
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

  it('renders ONLY the suggested_actions the FE can drive (no dead place_edge button)', async () => {
    listTriageMock.mockResolvedValue({ groups: [GROUP_EDGE_MISMATCH] });
    render(<TriageQueue projectId="p-1" />, { wrapper: Wrapper });
    await waitFor(() =>
      expect(screen.getByTestId('kg-triage-group')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('kg-triage-action-re_target')).toBeInTheDocument();
    expect(screen.getByTestId('kg-triage-action-widen_target_kinds')).toBeInTheDocument();
    expect(screen.getByTestId('kg-triage-action-drop_edge')).toBeInTheDocument();
    // place_edge is a confirm-token flow, not a resolve action → never a button.
    expect(screen.queryByTestId('kg-triage-action-place_edge')).not.toBeInTheDocument();
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

  it('re_target prompts for the corrected target and passes it as params', async () => {
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('ent-99');
    listTriageMock.mockResolvedValue({ groups: [GROUP_EDGE_MISMATCH] });
    resolveTriageMock.mockResolvedValue({ status: 'resolved', affected: 1 });
    render(<TriageQueue projectId="p-1" />, { wrapper: Wrapper });
    await waitFor(() => screen.getByTestId('kg-triage-action-re_target'));
    fireEvent.click(screen.getByTestId('kg-triage-action-re_target'));
    await waitFor(() =>
      expect(resolveTriageMock).toHaveBeenCalledWith(
        'p-1', 'sig-1',
        { action: 're_target', params: { target_entity_id: 'ent-99' } },
        'tok',
      ),
    );
    promptSpy.mockRestore();
  });

  it('re_target with a blank prompt does NOT fire (no silent no-op)', async () => {
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('   ');
    listTriageMock.mockResolvedValue({ groups: [GROUP_EDGE_MISMATCH] });
    render(<TriageQueue projectId="p-1" />, { wrapper: Wrapper });
    await waitFor(() => screen.getByTestId('kg-triage-action-re_target'));
    fireEvent.click(screen.getByTestId('kg-triage-action-re_target'));
    await new Promise((r) => setTimeout(r, 20));
    expect(resolveTriageMock).not.toHaveBeenCalled();
    promptSpy.mockRestore();
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
});
