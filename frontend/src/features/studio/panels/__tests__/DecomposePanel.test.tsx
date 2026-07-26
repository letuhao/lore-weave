// S-13 — the studio decompose panel is a HOST over the existing PlannerView/usePlanner flow. These
// tests prove the three things the host owns: the no-Work empty state (not a dead-end), mounting the
// real planner when a Work resolves, and threading the deep-linked templateId (pre-select).
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { IDockviewPanelProps } from 'dockview-react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 't' }) }));
vi.mock('../../host/StudioHostProvider', () => ({ useStudioHost: () => ({ bookId: 'b1' }) }));
vi.mock('../useStudioPanel', () => ({ useStudioPanel: () => 'decompose' }));
vi.mock('../WorkSetupCta', () => ({ WorkSetupCta: (p: { bookId: string }) => <div data-testid="work-setup-cta-stub" data-book={p.bookId} /> }));

const plannerProps = vi.hoisted(() => ({ value: null as Record<string, unknown> | null }));
vi.mock('@/features/composition/components/PlannerView', () => ({
  PlannerView: (p: Record<string, unknown>) => { plannerProps.value = p; return <div data-testid="planner-view-stub" />; },
}));

const work = vi.hoisted(() => ({ value: { data: undefined as unknown, isLoading: false, isError: false, refetch: vi.fn() } }));
const active = vi.hoisted(() => ({ value: null as { project_id: string; settings: Record<string, unknown> } | null }));
vi.mock('@/features/composition/hooks/useWork', () => ({ useWorkResolution: () => work.value }));
vi.mock('@/features/composition/hooks/useActiveWork', () => ({ useActiveWorkId: () => ({ data: undefined }) }));
vi.mock('@/features/composition/workSelect', () => ({ resolveActiveWork: () => active.value }));

import { DecomposePanel } from '../DecomposePanel';

const props = (params?: Record<string, unknown>): IDockviewPanelProps =>
  ({ api: { onDidParametersChange: undefined }, params } as unknown as IDockviewPanelProps);

beforeEach(() => {
  plannerProps.value = null;
  work.value = { data: {}, isLoading: false, isError: false, refetch: vi.fn() };
  active.value = null;
});

describe('DecomposePanel', () => {
  it('shows a loading hint while the work resolves (not a blank pane)', () => {
    work.value = { data: undefined, isLoading: true };
    render(<DecomposePanel {...props()} />);
    expect(screen.getByTestId('decompose-loading')).toBeInTheDocument();
  });

  it('no Work → the WorkSetupCta (ENTRY-from-empty, not a dead-end)', () => {
    active.value = null;   // resolveActiveWork → null → no project_id
    render(<DecomposePanel {...props()} />);
    expect(screen.getByTestId('decompose-no-work')).toBeInTheDocument();
    expect(screen.getByTestId('work-setup-cta-stub')).toHaveAttribute('data-book', 'b1');
    expect(screen.queryByTestId('planner-view-stub')).toBeNull();
  });

  it('with a Work → mounts the real PlannerView against its project_id + the work default model', () => {
    active.value = { project_id: 'p1', settings: { default_model_ref: 'model-x' } };
    render(<DecomposePanel {...props()} />);
    expect(screen.getByTestId('planner-view-stub')).toBeInTheDocument();
    expect(plannerProps.value?.projectId).toBe('p1');
    expect(plannerProps.value?.modelRef).toBe('model-x');
    expect(plannerProps.value?.initialTemplateId).toBeUndefined();   // no deep-link → normal picker
  });

  it('the templateId open-param is threaded to PlannerView as initialTemplateId (pre-select)', () => {
    active.value = { project_id: 'p1', settings: {} };
    render(<DecomposePanel {...props({ templateId: 'tpl-42' })} />);
    expect(plannerProps.value?.initialTemplateId).toBe('tpl-42');
    expect(plannerProps.value?.modelRef).toBe('');   // no work default → '' (planner's local picker covers it)
  });

  // review-impl LOW-1 — a LOAD FAILURE must not masquerade as "no Work" (which would tell the user to
  // create a Work that may already exist). Show an error + retry, not the setup CTA.
  it('a work-load error shows an error + retry (not the setup CTA)', () => {
    const refetch = vi.fn();
    work.value = { data: undefined, isLoading: false, isError: true, refetch };
    render(<DecomposePanel {...props()} />);
    expect(screen.getByTestId('decompose-error')).toBeInTheDocument();
    expect(screen.queryByTestId('decompose-no-work')).toBeNull();
    fireEvent.click(screen.getByTestId('decompose-retry'));
    expect(refetch).toHaveBeenCalled();
  });

  // review-impl MED-1 — DOCK-6: an already-open panel retargets via onDidParametersChange, re-seeding
  // the new deep-linked template (a second "Use in decompose" while decompose is already open).
  it('retargets the pre-selected template when the open-param changes (already-open panel)', () => {
    active.value = { project_id: 'p1', settings: {} };
    let paramCb: ((n: Record<string, unknown> | undefined) => void) | undefined;
    const api = { onDidParametersChange: (cb: (n: Record<string, unknown> | undefined) => void) => { paramCb = cb; return { dispose: vi.fn() }; } };
    render(<DecomposePanel {...({ api, params: { templateId: 'first' } } as unknown as IDockviewPanelProps)} />);
    expect(plannerProps.value?.initialTemplateId).toBe('first');
    act(() => paramCb?.({ templateId: 'second' }));   // openPanel updateParameters on the open singleton
    expect(plannerProps.value?.initialTemplateId).toBe('second');
  });
});
