import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CompositionPanel } from '../CompositionPanel';

// C28 (dị bản M6) — the living-world tree deep-links into a SPECIFIC Work via
// `?work=<surrogate id>`. A canon + its dị bản share one book_id (COW), so the
// param must disambiguate WHICH candidate the panel opens. These tests assert
// the panel resolves the named candidate (not just candidates[0]) and falls back
// safely when the param is absent/stale — DERIVED inline (no useEffect).

// Probe the resolved Work by reporting its project_id through the DerivativeBanner
// mock (it receives the derivative context derived from the active work).
const seen = vi.hoisted(() => ({ projectId: '' }));
vi.mock('../DerivativeBanner', () => ({
  DerivativeBanner: () => null,
}));
// ComposeView receives the active projectId — surface it for the assertion.
vi.mock('../ComposeView', () => ({
  ComposeView: (props: { projectId?: string }) => {
    seen.projectId = props.projectId ?? '';
    return <div data-testid="compose-active" data-project={props.projectId} />;
  },
}));
// Stub the remaining heavy sub-panels (vi.mock is hoisted — must be literal).
vi.mock('../CoWriterChat', () => ({ CoWriterChat: () => null }));
vi.mock('../ChapterAssembleView', () => ({ ChapterAssembleView: () => null }));
vi.mock('../PlannerView', () => ({ PlannerView: () => null }));
vi.mock('../BeatSheetView', () => ({ BeatSheetView: () => null }));
vi.mock('../SceneGraphCanvas', () => ({ SceneGraphCanvas: () => null }));
vi.mock('../CastCodexPanel', () => ({ CastCodexPanel: () => null }));
vi.mock('../RelationshipMap', () => ({ RelationshipMap: () => null }));
vi.mock('../TimelineView', () => ({ TimelineView: () => null }));
vi.mock('../CharacterArcView', () => ({ CharacterArcView: () => null }));
vi.mock('../WorldMap', () => ({ WorldMap: () => null }));
vi.mock('../GroundingPanel', () => ({ GroundingPanel: () => null }));
vi.mock('../CanonRulesPanel', () => ({ CanonRulesPanel: () => null }));
vi.mock('../QualityPanel', () => ({ QualityPanel: () => null }));
vi.mock('../CompositionSettingsView', () => ({ CompositionSettingsView: () => null }));
vi.mock('../ThreadsPanel', () => ({ ThreadsPanel: () => null }));

const canon = { id: 'w-canon', project_id: 'proj-canon', book_id: 'b', settings: {} as Record<string, unknown>, source_work_id: null };
const deriv = { id: 'w-d1', project_id: 'proj-d1', book_id: 'b', settings: {} as Record<string, unknown>, source_work_id: 'w-canon', branch_point: 2 };

vi.mock('../../hooks/useWork', () => ({
  // a canon + a derivative on the same book → `candidates`.
  useWorkResolution: () => ({ data: { status: 'candidates', work: null, candidates: [canon, deriv] }, isLoading: false }),
  useCreateWork: () => ({ mutate: vi.fn(), isPending: false }),
  useChapterScenes: () => ({ data: [] }),
  useCreateScene: () => ({ mutate: vi.fn(), isPending: false }),
  useSetSceneStatus: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('../../../ai-models/api', () => ({
  aiModelsApi: { listUserModels: vi.fn().mockResolvedValue({ items: [] }) },
}));

function renderAt(entries: string[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={entries}>
        <CompositionPanel bookId="b" chapterId="c" token="tok" onAccept={vi.fn()} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => { seen.projectId = ''; });

describe('CompositionPanel ?work= deep-link (C28 living-world navigation)', () => {
  it('opens the NAMED dị bản candidate, not candidates[0]', () => {
    renderAt(['/books/b?work=w-d1']);
    // the derivative (proj-d1) is selected even though the canon is candidates[0].
    expect(screen.getByTestId('compose-active').getAttribute('data-project')).toBe('proj-d1');
  });

  it('opens the canon when ?work= names it', () => {
    renderAt(['/books/b?work=w-canon']);
    expect(screen.getByTestId('compose-active').getAttribute('data-project')).toBe('proj-canon');
  });

  it('falls back to candidates[0] when ?work= is absent', () => {
    renderAt(['/books/b']);
    expect(screen.getByTestId('compose-active').getAttribute('data-project')).toBe('proj-canon');
  });

  it('falls back to candidates[0] when ?work= is stale (no match)', () => {
    renderAt(['/books/b?work=does-not-exist']);
    expect(screen.getByTestId('compose-active').getAttribute('data-project')).toBe('proj-canon');
  });
});
