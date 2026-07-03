import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

// Pin a stable book scope so the panel renders without a real provider tree.
vi.mock('../../context/EnrichmentContext', () => ({
  useEnrichmentContext: () => ({
    bookId: 'book-1',
    activePanel: 'gaps',
    setActivePanel: vi.fn(),
    selectedProposalId: null,
    setSelectedProposalId: vi.fn(),
    projectFilter: null,
    setProjectFilter: vi.fn(),
    gapCount: null,
    setGapCount: vi.fn(),
  }),
}));

// Control the gaps data hook so we can drive gaps/detecting/enriching and spy.
const detectMock = vi.fn();
const autoEnrichMock = vi.fn();
const gapsState = vi.hoisted(() => ({
  gaps: null as unknown,
  needsExtraction: false,
  detecting: false,
  enriching: false,
}));
vi.mock('../../hooks/useGaps', () => ({
  useGaps: () => ({
    gaps: gapsState.gaps,
    needsExtraction: gapsState.needsExtraction,
    detect: (...a: unknown[]) => detectMock(...a),
    detecting: gapsState.detecting,
    autoEnrich: (...a: unknown[]) => autoEnrichMock(...a),
    enriching: gapsState.enriching,
  }),
}));

// GapsPanel reads chat + embedding models via the consolidated W5 hook, which
// fetches through aiModelsApi.listUserModels (keep the actual module for types
// + getUserModelMeta).
const listModelsMock = vi.fn();
vi.mock('@/features/ai-models/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/ai-models/api')>();
  return {
    ...actual,
    aiModelsApi: {
      listUserModels: (...a: unknown[]) => listModelsMock(...a),
      patchFavorite: vi.fn(),
    },
  };
});

// GapsPanel now uses the shared ModelPicker (was a raw <select>). Stub it with a
// button per capability that selects 'm1' — the established pattern.
vi.mock('@/components/model-picker', () => ({
  ModelPicker: ({ capability, onChange }: { capability: string; onChange: (id: string | null) => void }) => (
    <button type="button" data-testid={`gaps-pick-${capability}`} onClick={() => onChange('m1')}>
      pick {capability}
    </button>
  ),
}));

import { invalidateUserModelsCache } from '@/components/model-picker/useUserModels';
import { GapsPanel } from '../GapsPanel';
import type { Gap } from '../../types';

const G = (over: Partial<Gap> = {}): Gap =>
  ({
    rank: 1,
    score: 0.82,
    canonical_name: '玉虛宮',
    entity_kind: 'location',
    mention_count: 4,
    present_dimensions: ['name'],
    missing_dimensions: ['appearance', 'history'],
    ...over,
  } as Gap);

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<GapsPanel />, { wrapper: Wrapper });
}

// Pick a model via the stubbed ModelPicker (clicks select 'm1' for that capability).
function selectModel(capability: 'chat' | 'embedding') {
  fireEvent.click(screen.getByTestId(`gaps-pick-${capability}`));
}

beforeEach(() => {
  detectMock.mockReset();
  autoEnrichMock.mockReset();
  listModelsMock.mockReset();
  invalidateUserModelsCache(); // the shared hook keeps a short-TTL module cache
  gapsState.gaps = null;
  gapsState.needsExtraction = false;
  gapsState.detecting = false;
  gapsState.enriching = false;
  // Both capabilities resolve to the same single model so either select can pick it.
  listModelsMock.mockResolvedValue({
    items: [{ user_model_id: 'm1', alias: 'qwen', provider_model_name: 'qwen' }],
  });
});

describe('GapsPanel', () => {
  it('gaps === null shows the detect hint and no table', () => {
    renderPanel();
    expect(screen.getByText('gaps.detect_hint')).toBeInTheDocument();
    expect(screen.queryByText('gaps.none')).toBeNull();
    expect(screen.queryByText('gaps.col.entity')).toBeNull();
  });

  it('clicking the detect button calls detect()', () => {
    renderPanel();
    fireEvent.click(screen.getByTestId('enrichment-detect-gaps'));
    expect(detectMock).toHaveBeenCalledTimes(1);
  });

  it('gaps === [] shows the empty note', () => {
    gapsState.gaps = [];
    renderPanel();
    expect(screen.getByText('gaps.none')).toBeInTheDocument();
    expect(screen.getByTestId('enrichment-gaps-none')).toBeInTheDocument();
    expect(screen.queryByText('gaps.detect_hint')).toBeNull();
  });

  it('gaps === [] + needsExtraction shows the "extract first" message, not "no gaps" (C2/KB2)', () => {
    gapsState.gaps = [];
    gapsState.needsExtraction = true;
    renderPanel();
    expect(screen.getByTestId('enrichment-gaps-extract-first')).toBeInTheDocument();
    expect(screen.getByText('gaps.extract_first')).toBeInTheDocument();
    expect(screen.queryByText('gaps.none')).toBeNull();
  });

  it('with gaps renders a row per gap: name, kind, joined missing dims, score.toFixed(2)', () => {
    gapsState.gaps = [
      G(),
      G({
        canonical_name: '哪吒',
        entity_kind: 'character',
        missing_dimensions: ['lineage'],
        score: 0.5,
      }),
    ];
    renderPanel();
    expect(screen.getByText('玉虛宮')).toBeInTheDocument();
    expect(screen.getByText('location')).toBeInTheDocument();
    expect(screen.getByText('appearance·history')).toBeInTheDocument();
    expect(screen.getByText('0.82')).toBeInTheDocument();

    expect(screen.getByText('哪吒')).toBeInTheDocument();
    expect(screen.getByText('character')).toBeInTheDocument();
    expect(screen.getByText('lineage')).toBeInTheDocument();
    expect(screen.getByText('0.50')).toBeInTheDocument();
  });

  it('auto-enrich is disabled until BOTH gen and embed models are selected', async () => {
    renderPanel();
    const button = screen.getByText('gaps.auto_enrich').closest('button')!;
    expect(button).toBeDisabled();

    selectModel('chat');
    expect(button).toBeDisabled(); // embed still empty

    selectModel('embedding');
    expect(button).not.toBeDisabled();
  });

  it('clicking auto-enrich calls autoEnrich with the full body; empty cost-cap -> max_spend_tokens null', async () => {
    renderPanel();
    selectModel('chat');
    selectModel('embedding');

    // The cost-cap input exists and is left empty.
    const spend = screen.getByTestId('enrichment-max-spend');
    expect(spend).toBeInTheDocument();

    fireEvent.click(screen.getByText('gaps.auto_enrich').closest('button')!);

    expect(autoEnrichMock).toHaveBeenCalledTimes(1);
    expect(autoEnrichMock).toHaveBeenCalledWith({
      generation_model_ref: 'm1',
      embedding_model_ref: 'm1',
      technique: 'recook',
      max_gaps: 3,
      max_spend_tokens: null,
      top_k: 5,
    });
  });

  it('a filled cost-cap is forwarded as a number in max_spend_tokens', async () => {
    renderPanel();
    selectModel('chat');
    selectModel('embedding');
    fireEvent.change(screen.getByTestId('enrichment-max-spend'), { target: { value: '1.50' } });

    fireEvent.click(screen.getByText('gaps.auto_enrich').closest('button')!);

    expect(autoEnrichMock).toHaveBeenCalledWith(
      expect.objectContaining({ max_spend_tokens: 1.5 }),
    );
  });

  it('while enriching the button shows the enriching label and stays disabled', () => {
    gapsState.enriching = true;
    renderPanel();
    const button = screen.getByText('gaps.enriching').closest('button')!;
    expect(button).toBeDisabled();
    expect(screen.queryByText('gaps.auto_enrich')).toBeNull();
  });

  // LE-064 — the per-row "enrich →" enriches just that gap (targets), and is
  // disabled until both models are selected (same guard as the batch button).
  it('per-row enrich is disabled until models are picked, then enriches that one gap', async () => {
    gapsState.gaps = [G({ canonical_name: '玉虛宮' }), G({ canonical_name: '哪吒' })];
    renderPanel();
    const rowBtn = screen.getByTestId('enrichment-enrich-gap-玉虛宮');
    expect(rowBtn).toBeDisabled();

    selectModel('chat');
    selectModel('embedding');
    expect(rowBtn).not.toBeDisabled();

    fireEvent.click(rowBtn);
    expect(autoEnrichMock).toHaveBeenCalledTimes(1);
    expect(autoEnrichMock).toHaveBeenCalledWith(
      expect.objectContaining({
        generation_model_ref: 'm1',
        embedding_model_ref: 'm1',
        technique: 'recook',
        targets: [
          expect.objectContaining({
            canonical_name: '玉虛宮',
            target_ref: '玉虛宮',
            entity_kind: 'location',
            present_dimensions: ['name'],
          }),
        ],
      }),
    );
  });
});
