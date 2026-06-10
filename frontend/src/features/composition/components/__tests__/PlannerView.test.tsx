import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PlannerView } from '../PlannerView';

const { mockHook } = vi.hoisted(() => ({ mockHook: { current: null as unknown } }));
vi.mock('../../hooks/usePlanner', () => ({ usePlanner: () => mockHook.current }));
// FD-15 — PlannerView now fetches the glossary roster; mock it (no QueryClient in this harness).
vi.mock('../../hooks/useGlossaryRoster', () => ({
  useGlossaryRoster: () => ({ data: [{ id: 'e1', label: 'Kael' }], isLoading: false }),
}));

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const baseHook = (over: Record<string, unknown> = {}): any => ({
  templates: { data: [{ id: 't1', name: 'Three-Act' }] },
  templateId: '', setTemplateId: vi.fn(),
  premise: '', setPremise: vi.fn(),
  arcTitle: 'Arc', draft: null, preview: null, totalScenes: 0,
  previewing: false, committing: false, error: null, needsReplace: null,
  cancelReplace: vi.fn(), runPreview: vi.fn(),
  editScene: vi.fn(), editChapter: vi.fn(), addScene: vi.fn(), removeScene: vi.fn(),
  commit: vi.fn(), confirmReplace: vi.fn(),
  ...over,
});

const DRAFT = [{ chapter_id: 'ch1', title: 'Ch1', intent: '', beat_role: null, scenes: [{ title: 'S1', synopsis: '', tension: 50, present_entity_ids: [] }] }];
const PREVIEW = { arc_title: 'A', chapters: [{ chapter: { chapter_id: 'ch1', title: 'Ch1', sort_order: 1, beat_role: null, intent: '' }, scenes: [{ title: 'S1', synopsis: '', tension: 50, present_entity_ids: [], present_entity_names_unresolved: [], suggested_k: 1 }], warning: null }], unmapped_beats: [] };
const MODELS = [{ user_model_id: 'm1', provider_model_name: 'gpt-4o' }];

beforeEach(() => { mockHook.current = baseHook(); });

describe('PlannerView', () => {
  it('shows the config form when there is no draft', () => {
    render(<PlannerView projectId="p" bookId="b" modelRef="m" token="t" />);
    expect(screen.getByTestId('planner-view')).toBeTruthy();
  });

  it('renders the editable tree + commit when a draft exists', () => {
    mockHook.current = baseHook({ draft: DRAFT, preview: PREVIEW, totalScenes: 1 });
    render(<PlannerView projectId="p" bookId="b" modelRef="m" token="t" />);
    expect(screen.getByDisplayValue('S1')).toBeTruthy();
    expect(screen.getByTestId('planner-beat-role')).toBeTruthy(); // FD-15 beat_role editable
  });

  it('shows the replace-confirm dialog on a 409', () => {
    mockHook.current = baseHook({ draft: DRAFT, preview: PREVIEW, totalScenes: 1, needsReplace: ['ch1'] });
    render(<PlannerView projectId="p" bookId="b" modelRef="m" token="t" />);
    expect(screen.getByRole('alertdialog')).toBeTruthy();
  });

  it('FD-15: a planner-local model override is passed to runPreview', () => {
    const runPreview = vi.fn();
    mockHook.current = baseHook({ templateId: 't1', premise: 'a premise', runPreview });
    render(<PlannerView projectId="p" bookId="b" modelRef="panel-model" models={MODELS} token="t" />);
    fireEvent.change(screen.getByTestId('planner-model'), { target: { value: 'm1' } });
    fireEvent.click(screen.getByRole('button', { name: /preview/i }));
    expect(runPreview).toHaveBeenCalledWith({ modelRef: 'm1', modelSource: 'user_model' });
  });

  it('FD-15: editing beat_role bubbles to editChapter', () => {
    const editChapter = vi.fn();
    mockHook.current = baseHook({ draft: DRAFT, preview: PREVIEW, totalScenes: 1, editChapter });
    render(<PlannerView projectId="p" bookId="b" modelRef="m" token="t" />);
    fireEvent.change(screen.getByTestId('planner-beat-role'), { target: { value: 'Climax' } });
    expect(editChapter).toHaveBeenCalledWith(0, { beat_role: 'Climax' });
  });
});
