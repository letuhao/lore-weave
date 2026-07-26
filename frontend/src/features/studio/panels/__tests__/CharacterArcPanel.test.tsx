// s7-4 — CharacterArcPanel wrapper: resolves its subject via props.params.entityId
// (DP-5 tier 1) and hands it to the leaf <CharacterArcView>. The leaf is stubbed.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { IDockviewPanelProps } from 'dockview-react';
import type { ReactNode } from 'react';
import { StudioHostProvider, useStudioHost, type StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }) }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: Record<string, unknown>) => String(o?.defaultValue ?? k) }),
}));

vi.mock('@/features/composition/components/CharacterArcView', () => ({
  CharacterArcView: (props: { entityId: string | null; chapterId: string }) => (
    <div data-testid="arc-view-stub" data-entity={props.entityId ?? ''} data-chapter={props.chapterId} />
  ),
}));
vi.mock('@/features/knowledge/components/EntityEditDialog', () => ({ EntityEditDialog: () => null }));
vi.mock('@/features/knowledge/components/CreateRelationDialog', () => ({ CreateRelationDialog: () => null }));

const useEntityDetail = vi.fn();
vi.mock('@/features/knowledge/hooks/useEntityDetail', () => ({
  useEntityDetail: () => useEntityDetail(),
}));

import { CharacterArcPanel } from '../CharacterArcPanel';

function dockProps(params?: Record<string, unknown>) {
  return { api: { setTitle: vi.fn() }, params } as unknown as IDockviewPanelProps;
}
function withHost(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <StudioHostProvider bookId="b1">{ui}</StudioHostProvider>
    </QueryClientProvider>,
  );
}

describe('CharacterArcPanel wrapper', () => {
  beforeEach(() => {
    useEntityDetail.mockReturnValue({ detail: null });
  });

  it('seeds the leaf subject from props.params.entityId (deep-link tier 1)', () => {
    withHost(<CharacterArcPanel {...dockProps({ entityId: 'e42' })} />);
    expect(screen.getByTestId('arc-view-stub').getAttribute('data-entity')).toBe('e42');
  });

  it('a bare open (no param) leaves the leaf to its own picker (null subject, not a dead panel)', () => {
    withHost(<CharacterArcPanel {...dockProps()} />);
    expect(screen.getByTestId('arc-view-stub').getAttribute('data-entity')).toBe('');
  });

  it('renders the Edit/+link toolbar once the entity detail resolves', () => {
    useEntityDetail.mockReturnValue({
      detail: { entity: { id: 'e42', name: 'Kai', kind: 'character', project_id: 'p1', version: 1 } },
    });
    withHost(<CharacterArcPanel {...dockProps({ entityId: 'e42' })} />);
    expect(screen.getByTestId('arc-edit-entity')).toBeTruthy();
    expect(screen.getByTestId('arc-link-entity')).toBeTruthy();
  });

  // D-CAST-ARC-BUS-SLICE — tier-2 live update.
  it('an already-open panel re-subjects when a cast row publishes a castEntity bus event', () => {
    let host: StudioHost | null = null;
    function Capture() { host = useStudioHost(); return null; }
    withHost(<><Capture /><CharacterArcPanel {...dockProps()} /></>);
    // Bare open → the leaf has no subject yet (its own picker, not a dead panel).
    expect(screen.getByTestId('arc-view-stub').getAttribute('data-entity')).toBe('');
    // A cast-row "view arc" click publishes the bus event → the open panel switches.
    act(() => { host!.publish({ type: 'castEntity', entityId: 'e99' }); });
    expect(screen.getByTestId('arc-view-stub').getAttribute('data-entity')).toBe('e99');
  });

  it('a deep-link param wins over the bus (tier-1 precedence, picker still available)', () => {
    let host: StudioHost | null = null;
    function Capture() { host = useStudioHost(); return null; }
    withHost(<><Capture /><CharacterArcPanel {...dockProps({ entityId: 'e42' })} /></>);
    act(() => { host!.publish({ type: 'castEntity', entityId: 'e99' }); });
    // params.entityId is tier-1; the bus is tier-2 → the param subject holds.
    expect(screen.getByTestId('arc-view-stub').getAttribute('data-entity')).toBe('e42');
  });
});
