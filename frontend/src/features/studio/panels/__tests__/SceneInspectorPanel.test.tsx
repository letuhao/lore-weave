// 22-C3 panel-shell test: the inspector renders the sectioned form for the selected node, edits
// commit via the hook's OCC patch, and the no-selection empty state shows. The hook + GroundingPanel
// are mocked so this stays a pure view test (the hook's load/OCC is covered by useSceneInspector.test).
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider } from '../../host/StudioHostProvider';
import type { SceneInspectorState } from '../useSceneInspector';
import type { OutlineNode } from '@/features/composition/types';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));
vi.mock('@/features/composition/components/GroundingPanel', () => ({
  GroundingPanel: () => <div data-testid="mock-grounding" />,
}));
// The inspector renders SceneMotifsSection (TanStack query hooks; covered on its own).
// Stub it so this stays a pure view test without needing a QueryClientProvider.
vi.mock('@/features/composition/motif/components/SceneMotifsSection', () => ({
  SceneMotifsSection: () => <div data-testid="mock-scene-motifs" />,
}));
const state = vi.fn<[], SceneInspectorState>();
vi.mock('../useSceneInspector', () => ({ useSceneInspector: () => state() }));
// 26 IX-14 — the inspector also reads conformance; mock it (default: nothing dirty).
const dirtyChapters = { current: new Set<string>() };
vi.mock('../useConformanceStatus', () => ({
  useConformanceStatus: () => ({
    status: null, dirtyChapters: dirtyChapters.current, staleChapterCount: 0,
    loading: false, error: null, refresh: vi.fn(),
  }),
}));
// 22-C3b — the inspector loads the glossary roster for the ref pickers; mock it (TanStack query
// would otherwise need a provider). Two book entities so pov/present/location resolve to names.
vi.mock('@/features/composition/hooks/useGlossaryRoster', () => ({
  useGlossaryRoster: () => ({ data: [{ id: 'e-anna', label: 'Anna' }, { id: 'e-bran', label: 'Bran' }], isLoading: false }),
}));
// 22-C3 Links — the inspector renders SceneLinksSection (TanStack hooks); mock them (covered on its own).
vi.mock('@/features/composition/hooks/useOutline', () => ({
  useSceneLinks: () => ({ data: [] }),
  useOutline: () => ({ data: [] }),
  useOutlineMutations: () => ({ createSceneLink: { mutate: vi.fn(), isPending: false }, deleteSceneLink: { mutate: vi.fn() } }),
}));

import { SceneInspectorPanel } from '../SceneInspectorPanel';

const node = (o: Partial<OutlineNode> = {}): OutlineNode => ({
  id: 'n1', project_id: 'p', parent_id: null, kind: 'scene', rank: 'a', title: 'Opening',
  chapter_id: 'ch1', story_order: 0, status: 'drafting', synopsis: 'the hero arrives', version: 3,
  is_archived: false, beat_role: 'inciting', goal: 'establish stakes', tension: 55, conflict: 'x',
  outcome: 'y', stakes: 'z', story_time: 'dawn', value_shift: -10, target_words: 900, source: 'decompiled', ...o,
});
const patch = vi.fn(async () => {});
const baseState = (o: Partial<SceneInspectorState>): SceneInspectorState => ({
  node: null, projectId: 'p', loading: false, error: null, saving: false, patch, ...o,
});

function dockProps() { return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps; }
function withHost(ui: ReactNode) { return render(<StudioHostProvider bookId="book-1">{ui}</StudioHostProvider>); }

beforeEach(() => { state.mockReset(); patch.mockClear(); dirtyChapters.current = new Set(); });

describe('SceneInspectorPanel (22-C3)', () => {
  it('shows the no-selection empty state when nothing is selected', () => {
    state.mockReturnValue(baseState({ node: null }));
    withHost(<SceneInspectorPanel {...dockProps()} />);
    expect(screen.getByText(/Select a scene/i)).toBeInTheDocument();
  });

  it('renders every section + the field values for the selected node', () => {
    state.mockReturnValue(baseState({ node: node() }));
    withHost(<SceneInspectorPanel {...dockProps()} />);
    expect((screen.getByTestId('scene-inspector-title') as HTMLInputElement).value).toBe('Opening');
    expect((screen.getByTestId('scene-inspector-goal') as HTMLInputElement).value).toBe('establish stakes');
    expect((screen.getByTestId('scene-inspector-tension') as HTMLInputElement).value).toBe('55');
    expect((screen.getByTestId('scene-inspector-conflict') as HTMLTextAreaElement).value).toBe('x');
    expect((screen.getByTestId('scene-inspector-targetwords') as HTMLInputElement).value).toBe('900');
    expect(screen.getByTestId('scene-inspector-source').textContent).toBe('Mined'); // decompiled → "Mined" badge
    expect(screen.getByTestId('mock-grounding')).toBeInTheDocument();
  });

  it('committing a changed intent field OCC-patches only that field', () => {
    state.mockReturnValue(baseState({ node: node() }));
    withHost(<SceneInspectorPanel {...dockProps()} />);
    const goal = screen.getByTestId('scene-inspector-goal');
    fireEvent.focus(goal);
    fireEvent.change(goal, { target: { value: 'raise the stakes' } });
    fireEvent.blur(goal);
    expect(patch).toHaveBeenCalledWith({ goal: 'raise the stakes' });
  });

  it('an unchanged field does NOT patch on blur', () => {
    state.mockReturnValue(baseState({ node: node() }));
    withHost(<SceneInspectorPanel {...dockProps()} />);
    const goal = screen.getByTestId('scene-inspector-goal');
    fireEvent.focus(goal);
    fireEvent.blur(goal);
    expect(patch).not.toHaveBeenCalled();
  });

  it('a tension number commits as a number; clearing it commits null', () => {
    state.mockReturnValue(baseState({ node: node() }));
    withHost(<SceneInspectorPanel {...dockProps()} />);
    const tension = screen.getByTestId('scene-inspector-tension');
    fireEvent.focus(tension);
    fireEvent.change(tension, { target: { value: '80' } });
    fireEvent.blur(tension);
    expect(patch).toHaveBeenCalledWith({ tension: 80 });

    patch.mockClear();
    fireEvent.focus(tension);
    fireEvent.change(tension, { target: { value: '' } });
    fireEvent.blur(tension);
    expect(patch).toHaveBeenCalledWith({ tension: null });
  });

  it('surfaces a save/load error', () => {
    state.mockReturnValue(baseState({ node: node(), error: 'changed elsewhere — reloaded' }));
    withHost(<SceneInspectorPanel {...dockProps()} />);
    expect(screen.getAllByTestId('scene-inspector-error')[0].textContent).toMatch(/changed elsewhere/);
  });

  it('22-C3b: renders the Cast & Setting refs and a POV pick OCC-patches pov_entity_id', () => {
    state.mockReturnValue(baseState({ node: node({ pov_entity_id: 'e-anna', present_entity_ids: ['e-bran'], location_entity_id: null }) }));
    withHost(<SceneInspectorPanel {...dockProps()} />);
    // POV resolves to the roster name (not a raw id).
    const pov = screen.getByTestId('scene-inspector-pov-select') as HTMLSelectElement;
    expect(pov.value).toBe('e-anna');
    // present shows a resolved chip (by testid — "Bran" also appears as <option> text elsewhere).
    expect(screen.getByTestId('scene-inspector-present-chip').textContent).toContain('Bran');
    // change POV → patches only that field.
    fireEvent.change(pov, { target: { value: 'e-bran' } });
    expect(patch).toHaveBeenCalledWith({ pov_entity_id: 'e-bran' });
  });

  it('26-F: shows the "canon moved" banner only when the scene\'s chapter is dirty', () => {
    state.mockReturnValue(baseState({ node: node({ chapter_id: 'ch1' }) }));
    const { queryByTestId } = withHost(<SceneInspectorPanel {...dockProps()} />);
    expect(queryByTestId('scene-inspector-dirty')).toBeNull(); // clean chapter → no banner

    dirtyChapters.current = new Set(['ch1']);
    withHost(<SceneInspectorPanel {...dockProps()} />);
    expect(screen.getByTestId('scene-inspector-dirty')).toBeInTheDocument();
  });
});
