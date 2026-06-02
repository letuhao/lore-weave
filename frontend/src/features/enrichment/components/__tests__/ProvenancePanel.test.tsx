import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
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

describe('ProvenancePanel', () => {
  it('renders the technique / confidence / origin / entity_kind fields', () => {
    render(<ProvenancePanel proposal={P({ technique: 'recook', confidence: 0.375, origin: 'enrichment', entity_kind: 'location' })} />);
    const container = screen.getByTestId('enrichment-provenance');
    expect(container).toBeInTheDocument();
    // field label keys
    expect(screen.getByText('prov.technique:')).toBeInTheDocument();
    expect(screen.getByText('prov.confidence:')).toBeInTheDocument();
    expect(screen.getByText('prov.origin:')).toBeInTheDocument();
    expect(screen.getByText('prov.entity_kind:')).toBeInTheDocument();
    // values (confidence is toFixed(2))
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
    render(<ProvenancePanel proposal={P({ source_refs_json: refs })} />);
    expect(screen.getByText('prov.grounding')).toBeInTheDocument();
    // first row: locator preferred
    expect(screen.getByText('封神演义·第三回')).toBeInTheDocument();
    // second row: falls back to corpus_id when no locator
    expect(screen.getByText('corpus-7')).toBeInTheDocument();
    // license tag keys
    expect(screen.getByText('license.public_domain')).toBeInTheDocument();
    expect(screen.getByText('license.unlicensed')).toBeInTheDocument();
    // score is toFixed(3)
    expect(screen.getByText('0.912')).toBeInTheDocument();
    expect(screen.getByText('0.500')).toBeInTheDocument();
  });

  it('omits the grounding section when there are no source refs', () => {
    render(<ProvenancePanel proposal={P({ source_refs_json: [] })} />);
    expect(screen.queryByText('prov.grounding')).toBeNull();
  });

  it('renders the skipped_unlicensed_sources section when present', () => {
    const skipped: SkippedSource[] = [
      { name: '某网文', license: 'copyrighted', reason: 'license=copyrighted' },
    ];
    render(<ProvenancePanel proposal={P({ provenance_json: { skipped_unlicensed_sources: skipped } })} />);
    expect(screen.getByText('prov.skipped')).toBeInTheDocument();
    expect(screen.getByText('某网文')).toBeInTheDocument();
    expect(screen.getByText('license.copyrighted')).toBeInTheDocument();
    expect(screen.getByText('license=copyrighted')).toBeInTheDocument();
  });

  it('omits the skipped section when none were skipped', () => {
    render(<ProvenancePanel proposal={P({ provenance_json: {} })} />);
    expect(screen.queryByText('prov.skipped')).toBeNull();
  });
});
