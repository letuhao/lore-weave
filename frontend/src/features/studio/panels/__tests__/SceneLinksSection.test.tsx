// 22-C3 Links — the inspector's causal-edge section resolves in/out edges to titles, adds a link
// FROM this scene, excludes self + already-outgoing targets from the picker, and deletes.
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { OutlineNode, SceneLink } from '@/features/composition/types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));

const links = { current: [] as SceneLink[] };
const nodes = { current: [] as OutlineNode[] };
const createMutate = vi.fn();
const deleteMutate = vi.fn();
vi.mock('@/features/composition/hooks/useOutline', () => ({
  useSceneLinks: () => ({ data: links.current }),
  useOutline: () => ({ data: nodes.current }),
  useOutlineMutations: () => ({
    createSceneLink: { mutate: createMutate, isPending: false },
    deleteSceneLink: { mutate: deleteMutate },
  }),
}));

import { SceneLinksSection } from '../SceneLinksSection';

const node = (id: string, title: string): OutlineNode => ({
  id, project_id: 'p', parent_id: null, kind: 'scene', rank: 'm', title, chapter_id: 'c',
  story_order: 0, status: 'drafting', synopsis: '', version: 1, is_archived: false, beat_role: null,
});
const link = (id: string, from: string, to: string, kind = 'setup_payoff', label = ''): SceneLink =>
  ({ id, from_node_id: from, to_node_id: to, kind: kind as SceneLink['kind'], label } as SceneLink);

beforeEach(() => {
  links.current = []; nodes.current = []; createMutate.mockReset(); deleteMutate.mockReset();
});

describe('SceneLinksSection (22-C3 Links)', () => {
  it('renders outgoing + incoming edges resolved to the endpoint scene titles', () => {
    nodes.current = [node('s1', 'The Meeting'), node('s2', 'The Payoff'), node('s0', 'The Setup')];
    links.current = [link('l1', 's1', 's2', 'setup_payoff', 'gun on the wall'), link('l2', 's0', 's1', 'custom')];
    render(<SceneLinksSection projectId="p" token="t" sceneId="s1" />);
    const rows = screen.getAllByTestId('scene-links-row');
    expect(rows).toHaveLength(2);
    // scope to the rows — a title can also appear as a <select> option below (excluded targets aside)
    expect(rows[0].textContent).toContain('The Payoff'); // outgoing target
    expect(rows[0].textContent).toContain('→');
    expect(rows[1].textContent).toContain('The Setup'); // incoming source
    expect(rows[1].textContent).toContain('←');
    expect(screen.getByText(/gun on the wall/)).toBeInTheDocument(); // label
  });

  it('the empty state shows when the scene has no links', () => {
    render(<SceneLinksSection projectId="p" token="t" sceneId="s1" />);
    expect(screen.getByText(/No causal links yet/)).toBeInTheDocument();
  });

  it('the empty state gates on THIS scene, not project-wide links (hint survives links elsewhere)', () => {
    // review fix: the project has a link between two OTHER scenes; the inspected scene has none.
    nodes.current = [node('s5', 'Focus'), node('s1', 'A'), node('s2', 'B')];
    links.current = [link('l1', 's1', 's2')];
    render(<SceneLinksSection projectId="p" token="t" sceneId="s5" />);
    expect(screen.getByText(/No causal links yet/)).toBeInTheDocument();
  });

  it('an empty-title endpoint renders a short-id, never a blank label', () => {
    // review fix: titleOf uses `||` so title==='' degrades to a short-id (like the picker).
    nodes.current = [node('s1', 'Here'), node('deadbeef-0000-0000', '')];
    links.current = [link('l1', 's1', 'deadbeef-0000-0000')];
    render(<SceneLinksSection projectId="p" token="t" sceneId="s1" />);
    expect(screen.getByTestId('scene-links-row').textContent).toContain('deadbeef…');
  });

  it('a scene already linked with a DIFFERENT kind is still offered (BE uniqueness is by kind)', () => {
    // review fix: the picker excludes only same-kind targets, so a second distinct-kind edge is addable.
    nodes.current = [node('s1', 'Here'), node('s2', 'There')];
    links.current = [link('l1', 's1', 's2', 'setup_payoff')]; // an existing setup_payoff edge
    render(<SceneLinksSection projectId="p" token="t" sceneId="s1" />);
    // default kind = setup_payoff → s2 excluded; switch to custom → s2 becomes offerable.
    let opts = Array.from((screen.getByTestId('scene-links-target') as HTMLSelectElement).options).map((o) => o.value);
    expect(opts).not.toContain('s2');
    fireEvent.change(screen.getByTestId('scene-links-kind'), { target: { value: 'custom' } });
    opts = Array.from((screen.getByTestId('scene-links-target') as HTMLSelectElement).options).map((o) => o.value);
    expect(opts).toContain('s2');
  });

  it('the add-target picker excludes self and already-outgoing targets', () => {
    nodes.current = [node('s1', 'Self'), node('s2', 'Linked'), node('s3', 'Free')];
    links.current = [link('l1', 's1', 's2')]; // s2 already an outgoing target
    render(<SceneLinksSection projectId="p" token="t" sceneId="s1" />);
    const opts = Array.from((screen.getByTestId('scene-links-target') as HTMLSelectElement).options).map((o) => o.value);
    expect(opts).not.toContain('s1'); // self excluded
    expect(opts).not.toContain('s2'); // already-outgoing excluded
    expect(opts).toContain('s3'); // free target offered
  });

  it('adding creates a link FROM this scene with the chosen kind + label', () => {
    nodes.current = [node('s1', 'Here'), node('s9', 'There')];
    render(<SceneLinksSection projectId="p" token="t" sceneId="s1" />);
    fireEvent.change(screen.getByTestId('scene-links-target'), { target: { value: 's9' } });
    fireEvent.change(screen.getByTestId('scene-links-kind'), { target: { value: 'custom' } });
    fireEvent.change(screen.getByTestId('scene-links-label'), { target: { value: 'echoes' } });
    fireEvent.click(screen.getByTestId('scene-links-add'));
    expect(createMutate).toHaveBeenCalledWith(
      { from_node_id: 's1', to_node_id: 's9', kind: 'custom', label: 'echoes' },
      expect.any(Object),
    );
  });

  it('the add button is disabled until a target is picked', () => {
    nodes.current = [node('s1', 'Here'), node('s9', 'There')];
    render(<SceneLinksSection projectId="p" token="t" sceneId="s1" />);
    expect(screen.getByTestId('scene-links-add')).toBeDisabled();
    fireEvent.change(screen.getByTestId('scene-links-target'), { target: { value: 's9' } });
    expect(screen.getByTestId('scene-links-add')).not.toBeDisabled();
  });

  it('removing a link deletes it by id', () => {
    nodes.current = [node('s1', 'Here'), node('s2', 'There')];
    links.current = [link('l1', 's1', 's2')];
    render(<SceneLinksSection projectId="p" token="t" sceneId="s1" />);
    fireEvent.click(screen.getByTestId('scene-links-remove-l1'));
    expect(deleteMutate).toHaveBeenCalledWith('l1');
  });
});
