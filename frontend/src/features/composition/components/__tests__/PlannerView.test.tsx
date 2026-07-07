import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { invalidateUserModelsCache } from '@/components/model-picker';
import { PlannerView } from '../PlannerView';

const { mockHook } = vi.hoisted(() => ({ mockHook: { current: null as unknown } }));
vi.mock('../../hooks/usePlanner', () => ({ usePlanner: () => mockHook.current }));
// FD-15 — PlannerView now fetches the glossary roster; mock it (no QueryClient in this harness).
vi.mock('../../hooks/useGlossaryRoster', () => ({
  useGlossaryRoster: () => ({ data: [{ id: 'e1', label: 'Kael' }], isLoading: false }),
}));

// D-PLANFORGE-MODEL-DROPDOWN — the local model override now renders the shared
// ModelPicker (was a bespoke <select>), so it fetches via aiModelsApi like every
// other picker in the app.
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('@/lib/syncPrefs', () => ({
  loadPrefFromServer: vi.fn().mockResolvedValue(undefined),
  savePrefToServer: vi.fn().mockResolvedValue(true),
  syncPrefsToServer: vi.fn(),
}));
const listUserModelsMock = vi.fn();
vi.mock('@/features/ai-models/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/ai-models/api')>();
  return {
    ...actual,
    aiModelsApi: {
      listUserModels: (...a: unknown[]) => listUserModelsMock(...a),
      patchFavorite: vi.fn(),
    },
  };
});

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
const MODELS = [{
  user_model_id: 'm1', provider_credential_id: 'c1', provider_kind: 'openai',
  provider_model_name: 'gpt-4o', alias: 'gpt-4o', is_active: true, is_favorite: false,
  capability_flags: { chat: true }, tags: [], created_at: '2026-01-01T00:00:00Z',
}];

beforeEach(() => {
  mockHook.current = baseHook();
  vi.clearAllMocks();
  invalidateUserModelsCache();
  listUserModelsMock.mockResolvedValue({ items: [] });
});

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

  it('FD-15: a planner-local model override (shared ModelPicker) is passed to runPreview', async () => {
    listUserModelsMock.mockResolvedValue({ items: MODELS });
    const runPreview = vi.fn();
    mockHook.current = baseHook({ templateId: 't1', premise: 'a premise', runPreview });
    render(<PlannerView projectId="p" bookId="b" modelRef="panel-model" token="t" />);
    const picker = () => within(screen.getByTestId('planner-model-picker'));
    await waitFor(() => expect(listUserModelsMock).toHaveBeenCalled());
    fireEvent.click(picker().getByRole('combobox'));
    fireEvent.click(await screen.findByRole('option', { name: /gpt-4o/ }));
    await waitFor(() => expect(picker().getByRole('combobox')).toHaveTextContent('gpt-4o'));
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
