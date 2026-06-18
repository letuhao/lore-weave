import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CompositionPanel } from '../CompositionPanel';

// C17 (WG-4) — guided first-run in the Compose container. A fresh book should reach
// a primed Generate in ≤2 clicks: the sole registered chat model is auto-picked, a
// contextual next-step cue renders, and when the Work has no scene a prominent
// "Start writing" action creates the first one. Auto-pick must fire ONLY for exactly
// one model (never 0/≥2).

function inert(name: string) {
  return function Mock() {
    return <div data-testid={`mock-${name}`}>{name}</div>;
  };
}
vi.mock('../ComposeView', () => ({ ComposeView: inert('compose') }));
vi.mock('../CoWriterChat', () => ({ CoWriterChat: inert('cowriter') }));
vi.mock('../ChapterAssembleView', () => ({ ChapterAssembleView: inert('assemble') }));
vi.mock('../PlannerView', () => ({ PlannerView: inert('planner') }));
vi.mock('../BeatSheetView', () => ({ BeatSheetView: inert('beats') }));
vi.mock('../SceneGraphCanvas', () => ({ SceneGraphCanvas: inert('graph') }));
vi.mock('../CastCodexPanel', () => ({ CastCodexPanel: inert('cast') }));
vi.mock('../RelationshipMap', () => ({ RelationshipMap: inert('relmap') }));
vi.mock('../TimelineView', () => ({ TimelineView: inert('timeline') }));
vi.mock('../CharacterArcView', () => ({ CharacterArcView: inert('arc') }));
vi.mock('../WorldMap', () => ({ WorldMap: inert('worldmap') }));
vi.mock('../GroundingPanel', () => ({ GroundingPanel: inert('grounding') }));
vi.mock('../CanonRulesPanel', () => ({ CanonRulesPanel: inert('canon') }));
vi.mock('../QualityPanel', () => ({ QualityPanel: inert('quality') }));
vi.mock('../CompositionSettingsView', () => ({ CompositionSettingsView: inert('settings') }));

const createSceneMutate = vi.fn();
const scenesState = { data: [] as Array<{ id: string; title: string; status: string }>, isLoading: false };
const work = { project_id: 'proj-1', book_id: 'b', settings: {} as Record<string, unknown> };
vi.mock('../../hooks/useWork', () => ({
  useWorkResolution: () => ({ data: { status: 'found', work }, isLoading: false }),
  useCreateWork: () => ({ mutate: vi.fn(), isPending: false }),
  useChapterScenes: () => scenesState,
  useCreateScene: () => ({ mutate: createSceneMutate, isPending: false }),
  useSetSceneStatus: () => ({ mutate: vi.fn(), isPending: false }),
  usePendingWorkResolver: () => ({ state: 'idle', start: vi.fn(), retry: vi.fn() }),
}));

const listUserModels = vi.fn();
vi.mock('../../../ai-models/api', () => ({
  aiModelsApi: { listUserModels: (...args: unknown[]) => listUserModels(...args) },
}));

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <CompositionPanel bookId="b" chapterId="c" token="tok" onAccept={vi.fn()} />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  createSceneMutate.mockReset();
  scenesState.data = [];
  scenesState.isLoading = false;
});

describe('CompositionPanel guided first-run (C17 WG-4)', () => {
  it('renders the guided cue + a "Start writing" action when the Work has no scene yet', async () => {
    scenesState.data = [];
    listUserModels.mockResolvedValue({
      items: [{ user_model_id: 'm1', is_active: true, alias: 'Qwen', provider_model_name: 'qwen2.5' }],
    });
    renderPanel();
    await waitFor(() => expect(screen.getByTestId('composition-guided-cue')).toBeInTheDocument());
    const start = screen.getByTestId('composition-guided-start');
    fireEvent.click(start);
    // The title is i18n-resolved; assert the scene targets this chapter with a non-empty title.
    expect(createSceneMutate).toHaveBeenCalledTimes(1);
    expect(createSceneMutate).toHaveBeenCalledWith(
      expect.objectContaining({ chapter_id: 'c', title: expect.any(String) }),
    );
  });

  it('auto-picks the sole chat model into the model selector', async () => {
    scenesState.data = [{ id: 's1', title: 'Scene 1', status: 'drafting' }];
    listUserModels.mockResolvedValue({
      items: [{ user_model_id: 'm1', is_active: true, alias: 'Qwen', provider_model_name: 'qwen2.5' }],
    });
    renderPanel();
    await waitFor(() => {
      const sel = screen.getByTestId('composition-model-select') as HTMLSelectElement;
      expect(sel.value).toBe('m1');
    });
  });

  it('does NOT auto-pick when two or more chat models exist (ambiguous → let the writer choose)', async () => {
    scenesState.data = [{ id: 's1', title: 'Scene 1', status: 'drafting' }];
    listUserModels.mockResolvedValue({
      items: [
        { user_model_id: 'm1', is_active: true, alias: 'Qwen', provider_model_name: 'qwen2.5' },
        { user_model_id: 'm2', is_active: true, alias: 'Llama', provider_model_name: 'llama3' },
      ],
    });
    renderPanel();
    await screen.findByTestId('composition-ready-to-draft');
    const sel = screen.getByTestId('composition-model-select') as HTMLSelectElement;
    expect(sel.value).toBe(''); // no auto-pick — the placeholder option
  });

  it('shows no guided cue when there is no chat model (the writer must register one first — C15 CTA)', async () => {
    scenesState.data = [];
    listUserModels.mockResolvedValue({ items: [] });
    renderPanel();
    await screen.findByTestId('composition-add-chat-model');
    expect(screen.queryByTestId('composition-guided-cue')).not.toBeInTheDocument();
  });
});
