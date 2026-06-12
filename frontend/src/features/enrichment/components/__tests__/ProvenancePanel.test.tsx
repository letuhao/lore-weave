import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const listModelsMock = vi.fn();
vi.mock('@/features/settings/api', () => ({
  providerApi: { listUserModels: (...a: unknown[]) => listModelsMock(...a) },
}));

import { ProvenancePanel } from '../ProvenancePanel';
import type { Proposal, SourceRef, SkippedSource } from '../../types';

const P = (over: Partial<Proposal> = {}): Proposal =>
  ({
    proposal_id: 'p-1',
    project_id: 'proj-9',
    entity_kind: 'location',
    origin: 'enrichment',
    technique: 'recook',
    content: '...',
    confidence: 0.375,
    provenance_json: {},
    source_refs_json: [],
    review_status: 'proposed',
    ...over,
  } as Proposal);

function renderProv(proposal: Proposal) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<ProvenancePanel proposal={proposal} />, { wrapper: Wrapper });
}

beforeEach(() => {
  listModelsMock.mockReset();
  listModelsMock.mockResolvedValue({ items: [] });
});

describe('ProvenancePanel', () => {
  it('renders the technique / confidence / origin / entity_kind fields', () => {
    renderProv(P({ technique: 'recook', confidence: 0.375, origin: 'enrichment', entity_kind: 'location' }));
    expect(screen.getByTestId('enrichment-provenance')).toBeInTheDocument();
    expect(screen.getByText('prov.technique:')).toBeInTheDocument();
    expect(screen.getByText('prov.confidence:')).toBeInTheDocument();
    expect(screen.getByText('prov.origin:')).toBeInTheDocument();
    expect(screen.getByText('prov.entity_kind:')).toBeInTheDocument();
    expect(screen.getByText('recook')).toBeInTheDocument();
    expect(screen.getByText('0.38')).toBeInTheDocument();
    expect(screen.getByText('enrichment')).toBeInTheDocument();
    expect(screen.getByText('location')).toBeInTheDocument();
  });

  it('renders a grounding row per source_refs_json with locator, license tag, and score', () => {
    const refs: SourceRef[] = [
      { locator: '封神演义·第三回', license: 'public_domain', score: 0.91234 },
      { corpus_id: 'corpus-7', license: 'unlicensed', score: 0.5 },
    ];
    renderProv(P({ source_refs_json: refs }));
    expect(screen.getByText('prov.grounding')).toBeInTheDocument();
    expect(screen.getByText('封神演义·第三回')).toBeInTheDocument();
    expect(screen.getByText('corpus-7')).toBeInTheDocument();
    expect(screen.getByText('license.public_domain')).toBeInTheDocument();
    expect(screen.getByText('license.unlicensed')).toBeInTheDocument();
    expect(screen.getByText('0.912')).toBeInTheDocument();
    expect(screen.getByText('0.500')).toBeInTheDocument();
  });

  it('omits the grounding section when there are no source refs', () => {
    renderProv(P({ source_refs_json: [] }));
    expect(screen.queryByText('prov.grounding')).toBeNull();
  });

  it('renders the skipped_unlicensed_sources section when present', () => {
    const skipped: SkippedSource[] = [
      { name: '某网文', license: 'copyrighted', reason: 'license=copyrighted' },
    ];
    renderProv(P({ provenance_json: { skipped_unlicensed_sources: skipped } }));
    expect(screen.getByText('prov.skipped')).toBeInTheDocument();
    expect(screen.getByText('某网文')).toBeInTheDocument();
    expect(screen.getByText('license.copyrighted')).toBeInTheDocument();
    expect(screen.getByText('license=copyrighted')).toBeInTheDocument();
  });

  it('omits the skipped section when none were skipped', () => {
    renderProv(P({ provenance_json: {} }));
    expect(screen.queryByText('prov.skipped')).toBeNull();
  });

  // LE-067 — the ② abstracted-facts attribution shows only for recook.
  it('renders the recook ② attribution for a recook proposal', () => {
    renderProv(P({ technique: 'recook' }));
    expect(screen.getByTestId('enrichment-prov-recook')).toBeInTheDocument();
    expect(screen.getByText('prov.recook_abstracted')).toBeInTheDocument();
  });

  it('omits the recook ② attribution for a non-recook proposal', () => {
    renderProv(P({ technique: 'fabrication' }));
    expect(screen.queryByTestId('enrichment-prov-recook')).toBeNull();
  });

  // LE-067 — resolves the gen model_ref (a user_model_id) to the friendly alias.
  it('resolves provenance_json.retrieval.model_ref to the model alias', async () => {
    listModelsMock.mockResolvedValue({
      items: [{ user_model_id: 'm-gen-1', alias: 'qwen3.6', provider_model_name: 'qwen' }],
    });
    renderProv(P({ provenance_json: { retrieval: { model_ref: 'm-gen-1' } } }));
    expect(screen.getByText('prov.model:')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('qwen3.6')).toBeInTheDocument());
  });

  it('omits the model field when no model_ref is present', () => {
    renderProv(P({ provenance_json: {} }));
    expect(screen.queryByText('prov.model:')).toBeNull();
  });
});
