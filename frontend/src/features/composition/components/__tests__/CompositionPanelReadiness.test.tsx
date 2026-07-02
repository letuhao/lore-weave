import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CompositionPanel } from '../CompositionPanel';

// C15 (WG-1/WG-2) — writer-unblock readiness affordances in the Compose container.
// The chat-model picker is the writer's ONE true prerequisite. When it's empty we
// must offer an in-flow register CTA (AddModelCta) — not a dead disabled select —
// and when a chat model exists we must surface a positive "Ready to draft" cue that
// frames knowledge/grounding as OPTIONAL (never a precondition wall). LOCKED WG-1/2/6.

// Keep the heavy sub-panels inert; we only assert the container's selector bar.
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

const work = { project_id: 'proj-1', book_id: 'b', settings: {} as Record<string, unknown> };
vi.mock('../../hooks/useWork', () => ({
  useWorkResolution: () => ({ data: { status: 'found', work }, isLoading: false }),
  useCreateWork: () => ({ mutate: vi.fn(), isPending: false }),
  useChapterScenes: () => ({ data: [{ id: 's1', title: 'Scene 1', status: 'drafting' }] }),
  useCreateScene: () => ({ mutate: vi.fn(), isPending: false }),
  useSetSceneStatus: () => ({ mutate: vi.fn(), isPending: false }),
  usePendingWorkResolver: () => ({ state: 'idle', start: vi.fn(), retry: vi.fn() }),
}));

const listUserModels = vi.fn();
// W5 — spread the real module: the shared ModelPicker also imports getUserModelMeta.
vi.mock('@/features/ai-models/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/ai-models/api')>();
  return {
    ...actual,
    aiModelsApi: { listUserModels: (...args: unknown[]) => listUserModels(...args), patchFavorite: vi.fn() },
  };
});
// W5 — the shared useUserModels/ModelPicker read the token from useAuth.
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('@/lib/syncPrefs', () => ({
  loadPrefFromServer: vi.fn().mockResolvedValue(undefined),
  savePrefToServer: vi.fn().mockResolvedValue(true),
  syncPrefsToServer: vi.fn(),
}));

import { invalidateUserModelsCache } from '@/components/model-picker';

beforeEach(() => {
  localStorage.clear();
  invalidateUserModelsCache();  // W5 — shared fetch cache must not leak across tests
});

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

describe('CompositionPanel writer-readiness (C15 WG-1/WG-2)', () => {
  it('renders an AddModelCta deep-link when the active chat-model list is empty', async () => {
    listUserModels.mockResolvedValue({ items: [] });
    renderPanel();
    const cta = await screen.findByTestId('composition-add-chat-model');
    // CTA must deep-link to model registration AND carry a return path (round-trip).
    const link = cta.querySelector('a');
    const href = link?.getAttribute('href') ?? '';
    expect(href).toContain('/settings/providers');
    expect(href).toContain('return=');
  });

  it('shows "Ready to draft" + optional-knowledge advisory once a chat model exists', async () => {
    listUserModels.mockResolvedValue({
      items: [{ user_model_id: 'm1', is_active: true, alias: 'Qwen', provider_model_name: 'qwen2.5' }],
    });
    renderPanel();
    await waitFor(() => expect(screen.getByTestId('composition-ready-to-draft')).toBeInTheDocument());
    // No CTA when a model is present.
    expect(screen.queryByTestId('composition-add-chat-model')).not.toBeInTheDocument();
  });

  it('never disables Generate / hides ComposeView when a chat model exists but knowledge is empty (WG-1/6 hard-block guard)', async () => {
    listUserModels.mockResolvedValue({
      items: [{ user_model_id: 'm1', is_active: true, alias: 'Qwen', provider_model_name: 'qwen2.5' }],
    });
    renderPanel();
    await screen.findByTestId('composition-ready-to-draft');
    // ComposeView (the Generate surface) is mounted and its wrapper is visible
    // (not hidden / not unmounted) — knowledge emptiness is advisory, never a wall.
    const compose = screen.getByTestId('mock-compose');
    expect(compose).toBeInTheDocument();
    expect(compose.parentElement).not.toHaveClass('hidden');
  });
});
