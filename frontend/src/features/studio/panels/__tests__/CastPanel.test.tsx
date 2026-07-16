// s7-4 — CastPanel wrapper: the deep-link seam (cast row → character-arc) and the
// edit-prop threading. The leaf <CastCodexPanel> is stubbed so the test isolates
// the WRAPPER's wiring (openPanel payload) — the leaf has its own coverage.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { IDockviewPanelProps } from 'dockview-react';
import type { ReactNode } from 'react';
import { StudioHostProvider, useStudioHost, type StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }) }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: Record<string, unknown>) => String(o?.defaultValue ?? k) }),
}));

// Stub the leaf: expose onViewArc + the edit-prop presence via test buttons.
vi.mock('@/features/composition/components/CastCodexPanel', () => ({
  CastCodexPanel: (props: {
    onViewArc?: (id: string) => void;
    onNewEntity?: () => void;
    onRename?: unknown;
    onEdit?: unknown;
    onArchive?: unknown;
  }) => (
    <div data-testid="cast-codex-stub">
      <button data-testid="stub-view-arc" onClick={() => props.onViewArc?.('e9')}>arc</button>
      <span data-testid="stub-has-rename">{props.onRename ? 'y' : 'n'}</span>
      <span data-testid="stub-has-edit">{props.onEdit ? 'y' : 'n'}</span>
      <span data-testid="stub-has-archive">{props.onArchive ? 'y' : 'n'}</span>
      <span data-testid="stub-has-new">{props.onNewEntity ? 'y' : 'n'}</span>
    </div>
  ),
}));
vi.mock('@/features/knowledge/components/EntityEditDialog', () => ({ EntityEditDialog: () => null }));
vi.mock('@/features/knowledge/components/CreateEntityDialog', () => ({ CreateEntityDialog: () => null }));

const useKnowledgeProjectId = vi.fn();
vi.mock('@/features/composition/hooks/useCast', () => ({
  useKnowledgeProjectId: () => useKnowledgeProjectId(),
}));
vi.mock('@/features/composition/hooks/useCastEdit', () => ({
  useCastEdit: () => ({ rename: vi.fn(), create: vi.fn(), link: vi.fn(), archive: vi.fn(), isPending: false }),
}));

import { CastPanel } from '../CastPanel';

function dockProps(params?: Record<string, unknown>) {
  return { api: { setTitle: vi.fn() }, params } as unknown as IDockviewPanelProps;
}
let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }
function withHost(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <StudioHostProvider bookId="b1"><HostProbe />{ui}</StudioHostProvider>
    </QueryClientProvider>,
  );
}

describe('CastPanel wrapper', () => {
  beforeEach(() => {
    hostRef = null;
    useKnowledgeProjectId.mockReturnValue({ data: 'proj-1' });
  });

  it('deep-links a cast row to character-arc with the entityId param (DP-5)', () => {
    withHost(<CastPanel {...dockProps()} />);
    const openSpy = vi.spyOn(hostRef!, 'openPanel');
    fireEvent.click(screen.getByTestId('stub-view-arc'));
    expect(openSpy).toHaveBeenCalledWith('character-arc', {
      params: { entityId: 'e9' },
      focus: true,
    });
  });

  it('threads the additive edit props + New (project resolved)', () => {
    withHost(<CastPanel {...dockProps()} />);
    expect(screen.getByTestId('stub-has-rename').textContent).toBe('y');
    expect(screen.getByTestId('stub-has-edit').textContent).toBe('y');
    expect(screen.getByTestId('stub-has-archive').textContent).toBe('y');
    expect(screen.getByTestId('stub-has-new').textContent).toBe('y');
  });

  it('disables + New when the book has no knowledge project', () => {
    useKnowledgeProjectId.mockReturnValue({ data: null });
    withHost(<CastPanel {...dockProps()} />);
    expect(screen.getByTestId('stub-has-new').textContent).toBe('n');
  });
});
