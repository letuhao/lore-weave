import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { BootstrapPanel } from '../BootstrapPanel';
import type { BootstrapProposal } from '../../types';

const noop = vi.fn();

const proposal = (over: Partial<BootstrapProposal> = {}): BootstrapProposal => ({
  id: 'p1', run_id: 'r1', book_id: 'b1', owner_user_id: 'u1', status: 'pending',
  diff: { new_chapters: [], new_glossary_entities: [] }, applied_results: {},
  error_detail: null, created_at: '', updated_at: '', ...over,
});

describe('BootstrapPanel', () => {
  it('idle state offers a "check what is needed" action, no raw JSON anywhere', () => {
    render(
      <BootstrapPanel proposal={null} busy={false} error={null}
        onPropose={noop} onApprove={noop} onReject={noop} onApply={noop} />,
    );
    expect(screen.getByTestId('bootstrap-panel-idle')).toBeTruthy();
    expect(screen.getByTestId('bootstrap-propose-btn')).toBeTruthy();
    expect(screen.queryByTestId('bootstrap-panel')).toBeNull();
  });

  it('renders new chapters and new glossary entities as plain cards, never raw JSON text', () => {
    render(
      <BootstrapPanel
        proposal={proposal({
          diff: {
            new_chapters: [{ event_id: 'e1', title: 'Chapter One', ordinal: 1, drafting_guide: '- Opening: hero wakes up.' }],
            new_glossary_entities: [{ name: 'Lin Feng', kind_code: 'character', attributes: { role: 'protagonist' } }],
          },
        })}
        busy={false} error={null} onPropose={noop} onApprove={noop} onReject={noop} onApply={noop}
      />,
    );
    const chapterCard = screen.getByTestId('bootstrap-new-chapter');
    expect(chapterCard.textContent).toContain('Chapter One');
    expect(chapterCard.textContent).toContain('hero wakes up');
    expect(chapterCard.textContent).not.toContain('{'); // no stringified JSON leaking through

    const glossaryCard = screen.getByTestId('bootstrap-new-glossary-entity');
    expect(glossaryCard.textContent).toContain('Lin Feng');
    expect(glossaryCard.textContent).toContain('Character'); // kind_code translated, not raw "character"...
    expect(glossaryCard.textContent).toContain('protagonist');

    // approve/reject are offered — there's real content to act on
    expect(screen.getByTestId('bootstrap-approve-btn')).toBeTruthy();
    expect(screen.getByTestId('bootstrap-reject-btn')).toBeTruthy();
  });

  it('an empty diff shows "nothing to do" and hides approve/reject', () => {
    render(
      <BootstrapPanel proposal={proposal()} busy={false} error={null}
        onPropose={noop} onApprove={noop} onReject={noop} onApply={noop} />,
    );
    expect(screen.getByTestId('bootstrap-nothing-to-do')).toBeTruthy();
    expect(screen.queryByTestId('bootstrap-approve-btn')).toBeNull();
  });

  it('approved status shows the apply action', () => {
    render(
      <BootstrapPanel
        proposal={proposal({ status: 'approved', diff: {
          new_chapters: [{ event_id: 'e1', title: 'Chapter One', ordinal: 1 }],
          new_glossary_entities: [],
        } })}
        busy={false} error={null} onPropose={noop} onApprove={noop} onReject={noop} onApply={noop}
      />,
    );
    expect(screen.getByTestId('bootstrap-apply-btn')).toBeTruthy();
    expect(screen.queryByTestId('bootstrap-approve-btn')).toBeNull();
  });

  it('applied status shows checkmarks against the items that were actually created', () => {
    render(
      <BootstrapPanel
        proposal={proposal({
          status: 'applied',
          diff: {
            new_chapters: [{ event_id: 'e1', title: 'Chapter One', ordinal: 1 }],
            new_glossary_entities: [],
          },
          applied_results: { e1: { chapter_id: 'c1', title: 'Chapter One' } },
        })}
        busy={false} error={null} onPropose={noop} onApprove={noop} onReject={noop} onApply={noop}
      />,
    );
    expect(screen.getByTestId('bootstrap-new-chapter').textContent).toContain('✓');
    expect(screen.getByTestId('bootstrap-applied-summary')).toBeTruthy();
  });

  it('failed status shows the actionable error_detail (never raw JSON) and a retry action, never a raw editor', () => {
    render(
      <BootstrapPanel
        proposal={proposal({
          status: 'failed',
          error_detail: 'This book has no Glossary ontology yet — adopt one in the Graph Schema tab, then retry apply.',
          diff: { new_chapters: [], new_glossary_entities: [{ name: 'Lin Feng', kind_code: 'character', attributes: {} }] },
        })}
        busy={false} error={null} onPropose={noop} onApprove={noop} onReject={noop} onApply={noop}
      />,
    );
    expect(screen.getByTestId('bootstrap-failed-detail').textContent).toContain('Graph Schema');
    expect(screen.getByTestId('bootstrap-retry-btn')).toBeTruthy();
    // LOCKED DESIGN PRINCIPLE: no raw spec/JSON editor as a failure fallback, ever.
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('a transient network error (distinct from a proposal-level failure) is shown too', () => {
    render(
      <BootstrapPanel proposal={proposal()} busy={false} error="network down"
        onPropose={noop} onApprove={noop} onReject={noop} onApply={noop} />,
    );
    expect(screen.getByTestId('bootstrap-error').textContent).toContain('network down');
  });
});
