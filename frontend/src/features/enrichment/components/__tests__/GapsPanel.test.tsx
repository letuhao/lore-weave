import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
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
  }),
}));

// Control the gaps data hook so we can drive gaps/detecting/enriching and spy.
const detectMock = vi.fn();
const autoEnrichMock = vi.fn();
const gapsState = vi.hoisted(() => ({
  gaps: null as unknown,
  detecting: false,
  enriching: false,
}));
vi.mock('../../hooks/useGaps', () => ({
  useGaps: () => ({
    gaps: gapsState.gaps,
    detect: (...a: unknown[]) => detectMock(...a),
    detecting: gapsState.detecting,
    autoEnrich: (...a: unknown[]) => autoEnrichMock(...a),
    enriching: gapsState.enriching,
  }),
}));

// GapsPanel reads chat + embedding models via providerApi.listUserModels.
const listModelsMock = vi.fn();
vi.mock('@/features/settings/api', () => ({
  providerApi: { listUserModels: (...a: unknown[]) => listModelsMock(...a) },
}));

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

// Pick a model in the gen/embed <select> by its preceding i18n-key label. The
// options come from an async useQuery, so await the option to mount before
// firing change (a native <select> ignores a value whose <option> isn't there).
async function selectModel(labelKey: string, userModelId: string, optionLabel: string) {
  const label = screen.getByText(labelKey).closest('label')!;
  const select = label.querySelector('select')!;
  await within(label).findByRole('option', { name: optionLabel });
  fireEvent.change(select, { target: { value: userModelId } });
}

beforeEach(() => {
  detectMock.mockReset();
  autoEnrichMock.mockReset();
  listModelsMock.mockReset();
  gapsState.gaps = null;
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
    expect(screen.queryByText('gaps.detect_hint')).toBeNull();
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

    await selectModel('gaps.gen_model', 'm1', 'qwen');
    expect(button).toBeDisabled(); // embed still empty

    await selectModel('gaps.embed_model', 'm1', 'qwen');
    expect(button).not.toBeDisabled();
  });

  it('clicking auto-enrich calls autoEnrich with the full body; empty cost-cap -> max_spend_usd null', async () => {
    renderPanel();
    await selectModel('gaps.gen_model', 'm1', 'qwen');
    await selectModel('gaps.embed_model', 'm1', 'qwen');

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
      max_spend_usd: null,
      top_k: 5,
    });
  });

  it('a filled cost-cap is forwarded as a number in max_spend_usd', async () => {
    renderPanel();
    await selectModel('gaps.gen_model', 'm1', 'qwen');
    await selectModel('gaps.embed_model', 'm1', 'qwen');
    fireEvent.change(screen.getByTestId('enrichment-max-spend'), { target: { value: '1.50' } });

    fireEvent.click(screen.getByText('gaps.auto_enrich').closest('button')!);

    expect(autoEnrichMock).toHaveBeenCalledWith(
      expect.objectContaining({ max_spend_usd: 1.5 }),
    );
  });

  it('while enriching the button shows the enriching label and stays disabled', () => {
    gapsState.enriching = true;
    renderPanel();
    const button = screen.getByText('gaps.enriching').closest('button')!;
    expect(button).toBeDisabled();
    expect(screen.queryByText('gaps.auto_enrich')).toBeNull();
  });
});
