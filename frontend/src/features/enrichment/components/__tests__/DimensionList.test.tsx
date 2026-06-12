import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DimensionList } from '../DimensionList';
import type { Proposal } from '../../types';

const P = (over: Partial<Proposal> = {}): Proposal =>
  ({
    proposal_id: 'p-1',
    project_id: 'proj-9',
    entity_kind: 'location',
    origin: 'enrichment',
    technique: 'recook',
    content: 'raw summary content',
    confidence: 0.4,
    provenance_json: {},
    source_refs_json: [],
    review_status: 'proposed',
    ...over,
  } as Proposal);

describe('DimensionList', () => {
  it('with no dimensions, falls back to the raw content in a <pre>', () => {
    const { container } = render(<DimensionList proposal={P({ content: 'raw summary content', provenance_json: {} })} />);
    expect(screen.queryByTestId('enrichment-dimensions')).toBeNull();
    const pre = container.querySelector('pre');
    expect(pre).not.toBeNull();
    expect(pre).toHaveTextContent('raw summary content');
  });

  it('treats an empty dimensions map the same as absent', () => {
    const { container } = render(<DimensionList proposal={P({ provenance_json: { dimensions: {} } })} />);
    expect(screen.queryByTestId('enrichment-dimensions')).toBeNull();
    expect(container.querySelector('pre')).not.toBeNull();
  });

  it('with a dimensions map, renders the dimensions container, count line, and one card per entry', () => {
    const dimensions = {
      历史: '商周交替的背景',
      地理: '朝歌城外的山水',
    };
    render(<DimensionList proposal={P({ provenance_json: { dimensions } })} />);
    expect(screen.getByTestId('enrichment-dimensions')).toBeInTheDocument();
    // the count line uses the detail.dimensions key
    expect(screen.getByText('detail.dimensions')).toBeInTheDocument();
    // one card per [dim, text]
    expect(screen.getByText('历史')).toBeInTheDocument();
    expect(screen.getByText('商周交替的背景')).toBeInTheDocument();
    expect(screen.getByText('地理')).toBeInTheDocument();
    expect(screen.getByText('朝歌城外的山水')).toBeInTheDocument();
    // no raw <pre> fallback when dimensions present
    expect(document.querySelector('pre')).toBeNull();
  });

  // LE-066 — beyond 3 dimensions, the rest collapse behind a toggle.
  it('collapses dimensions beyond 3 behind a toggle; expanding reveals the rest', () => {
    const dimensions = { 历史: 'h', 地理: 'g', 文化: 'c', features: 'f', inhabitants: 'i' };
    render(<DimensionList proposal={P({ provenance_json: { dimensions } })} />);
    // first 3 shown, last 2 hidden
    expect(screen.getByText('历史')).toBeInTheDocument();
    expect(screen.getByText('文化')).toBeInTheDocument();
    expect(screen.queryByText('features')).toBeNull();
    expect(screen.queryByText('inhabitants')).toBeNull();
    // the toggle reveals the rest
    const toggle = screen.getByTestId('enrichment-dimensions-toggle');
    expect(toggle).toHaveTextContent('detail.show_more');
    fireEvent.click(toggle);
    expect(screen.getByText('features')).toBeInTheDocument();
    expect(screen.getByText('inhabitants')).toBeInTheDocument();
    expect(toggle).toHaveTextContent('detail.show_less');
  });

  it('renders no toggle when there are 3 or fewer dimensions', () => {
    const dimensions = { 历史: 'h', 地理: 'g', 文化: 'c' };
    render(<DimensionList proposal={P({ provenance_json: { dimensions } })} />);
    expect(screen.queryByTestId('enrichment-dimensions-toggle')).toBeNull();
  });
});
