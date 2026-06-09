import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PlannerView } from '../PlannerView';

const { mockHook } = vi.hoisted(() => ({ mockHook: { current: null as unknown } }));
vi.mock('../../hooks/usePlanner', () => ({ usePlanner: () => mockHook.current }));

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

beforeEach(() => { mockHook.current = baseHook(); });

describe('PlannerView', () => {
  it('shows the config form when there is no draft', () => {
    render(<PlannerView projectId="p" modelRef="m" token="t" />);
    expect(screen.getByTestId('planner-view')).toBeTruthy();
    expect(screen.getByRole('combobox')).toBeTruthy(); // template select
  });

  it('renders the editable tree + commit when a draft exists', () => {
    mockHook.current = baseHook({ draft: DRAFT, preview: PREVIEW, totalScenes: 1 });
    render(<PlannerView projectId="p" modelRef="m" token="t" />);
    expect(screen.getByDisplayValue('S1')).toBeTruthy(); // editable scene-title input
  });

  it('shows the replace-confirm dialog on a 409', () => {
    mockHook.current = baseHook({ draft: DRAFT, preview: PREVIEW, totalScenes: 1, needsReplace: ['ch1'] });
    render(<PlannerView projectId="p" modelRef="m" token="t" />);
    expect(screen.getByRole('alertdialog')).toBeTruthy();
  });
});
