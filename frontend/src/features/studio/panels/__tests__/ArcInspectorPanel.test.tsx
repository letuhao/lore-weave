// 32 arc-inspector — the PANEL chrome's one branch that unit tests must pin: the empty-book gate.
// A LOADED detail must keep the body even when the shell is empty (getArcs excludes archived), so
// after archiving the last arc its Restore stays reachable. This regressed live once (the whole
// panel swapped to the "Open the Plan Hub" CTA and the archived arc vanished) — this locks it.
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

const ctrl = vi.hoisted(() => ({ useArcInspector: vi.fn() }));
vi.mock('../useArcInspector', () => ({ useArcInspector: ctrl.useArcInspector }));
vi.mock('../useStudioPanel', () => ({ useStudioPanel: () => {} }));
vi.mock('../../host/StudioHostProvider', () => ({ useStudioHost: () => ({ bookId: 'b', openPanel: vi.fn() }) }));
vi.mock('../ArcInspectorBody', () => ({ ArcInspectorBody: () => <div data-testid="arc-body-stub" /> }));

import { ArcInspectorPanel } from '../ArcInspectorPanel';
import type { IDockviewPanelProps } from 'dockview-react';

const props = { params: {} } as IDockviewPanelProps;

function state(over: Record<string, unknown> = {}) {
  return {
    arcId: null, select: vi.fn(), shell: [], detail: null, loading: false, error: null,
    saving: false, writeError: null, edit: vi.fn(), archive: vi.fn(), restore: vi.fn(),
    ancestors: [], blastRadius: 0, ...over,
  };
}

describe('ArcInspectorPanel · empty-book gate', () => {
  it('empty shell + NO detail → the empty-book CTA (nothing to inspect)', () => {
    ctrl.useArcInspector.mockReturnValue(state({ shell: [], detail: null }));
    render(<ArcInspectorPanel {...props} />);
    expect(screen.getByTestId('arc-inspector-empty-book')).toBeInTheDocument();
    expect(screen.queryByTestId('arc-body-stub')).toBeNull();
  });

  it('empty shell + a LOADED (archived) detail → the BODY stays (Restore reachable), NOT the CTA', () => {
    // the exact post-archive-last-arc state: getArcs excludes the archived arc so shell is empty,
    // but its detail is still loaded — the body must render so the user can Restore.
    ctrl.useArcInspector.mockReturnValue(state({ arcId: 'a1', shell: [], detail: { id: 'a1', is_archived: true } }));
    render(<ArcInspectorPanel {...props} />);
    expect(screen.getByTestId('arc-body-stub')).toBeInTheDocument();
    expect(screen.queryByTestId('arc-inspector-empty-book')).toBeNull();
  });

  it('a populated shell → the body (normal path)', () => {
    ctrl.useArcInspector.mockReturnValue(state({ arcId: 'a1', shell: [{ id: 'a1', depth: 0, kind: 'arc', title: 'A' }], detail: { id: 'a1' } }));
    render(<ArcInspectorPanel {...props} />);
    expect(screen.getByTestId('arc-body-stub')).toBeInTheDocument();
  });
});
