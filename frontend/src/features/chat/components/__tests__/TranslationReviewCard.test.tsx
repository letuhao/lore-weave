import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TranslationReviewCard, isTranslationProposeCall, summarizeTranslationReview } from '../TranslationReviewCard';
import type { ToolCallRecord } from '../types';

// S4 — the chat translation-review card renders the agent's class-W draft proposals
// (glossary_propose_translation / glossary_propose_aliases) inline so the human knows
// what was written and that it's a draft to verify in the Glossary editor.

function rec(partial: Partial<ToolCallRecord>): ToolCallRecord {
  return { tool: 'glossary_propose_translation', ok: true, ...partial };
}

describe('isTranslationProposeCall', () => {
  it('matches completed translation/alias proposals only', () => {
    expect(isTranslationProposeCall(rec({}))).toBe(true);
    expect(isTranslationProposeCall(rec({ tool: 'glossary_propose_aliases' }))).toBe(true);
    // pending → not yet (it's still a suspended frontend tool surface)
    expect(isTranslationProposeCall(rec({ pending: true }))).toBe(false);
    // failed → no review card
    expect(isTranslationProposeCall(rec({ ok: false }))).toBe(false);
    // unrelated tool
    expect(isTranslationProposeCall(rec({ tool: 'book_list' }))).toBe(false);
  });
});

describe('TranslationReviewCard', () => {
  it('renders proposed name translations with a draft badge + written count', () => {
    render(
      <TranslationReviewCard
        record={rec({
          args: { book_id: 'b1', language_code: 'en', items: [
            { entity_id: 'e1', value: 'Flame Demon' },
            { entity_id: 'e2', value: 'Yan Mo' },
          ] },
          result: { language_code: 'en', written: 2, skipped: 0, results: [] },
        })}
      />,
    );
    expect(screen.getByTestId('translation-review-card')).toBeInTheDocument();
    expect(screen.getByText('Flame Demon')).toBeInTheDocument();
    expect(screen.getByText('Yan Mo')).toBeInTheDocument();
    expect(screen.getByText('translation_review.draft')).toBeInTheDocument();
    // count interpolated by the test i18n mock
    expect(screen.getByText('translation_review.written')).toBeInTheDocument();
  });

  it('flattens alias arrays for glossary_propose_aliases and shows the aliases header', () => {
    render(
      <TranslationReviewCard
        record={rec({
          tool: 'glossary_propose_aliases',
          args: { book_id: 'b1', language_code: 'en', items: [
            { entity_id: 'e1', aliases: ['Flame Demon', 'Yan Mo'] },
          ] },
          result: { written: 1, skipped: 0 },
        })}
      />,
    );
    expect(screen.getByText('translation_review.header_aliases')).toBeInTheDocument();
    expect(screen.getByText('Flame Demon')).toBeInTheDocument();
    expect(screen.getByText('Yan Mo')).toBeInTheDocument();
  });

  it('caps the preview at 8 and shows a "+N more" affordance', () => {
    const items = Array.from({ length: 11 }, (_, i) => ({ entity_id: `e${i}`, value: `T${i}` }));
    render(
      <TranslationReviewCard
        record={rec({ args: { language_code: 'en', items }, result: { written: 11, skipped: 0 } })}
      />,
    );
    expect(screen.getByText('T0')).toBeInTheDocument();
    expect(screen.getByText('T7')).toBeInTheDocument();
    expect(screen.queryByText('T8')).not.toBeInTheDocument();
    expect(screen.getByText('translation_review.more')).toBeInTheDocument();
  });

  it('renders nothing for an empty/malformed record', () => {
    const { container } = render(<TranslationReviewCard record={rec({ args: {}, result: {} })} />);
    expect(container).toBeEmptyDOMElement();
  });
});

// /review-impl #1 — a sparse record (no args/result, e.g. a replayed {tool, ok}) must
// summarize to null so AssistantMessage keeps it as a chip instead of hiding it.
describe('summarizeTranslationReview', () => {
  it('returns null for a record with no renderable content', () => {
    expect(summarizeTranslationReview(rec({}))).toBeNull();
    expect(summarizeTranslationReview(rec({ args: {}, result: {} }))).toBeNull();
  });

  it('returns a summary when values or counts are present', () => {
    const s = summarizeTranslationReview(
      rec({ args: { language_code: 'en', items: [{ entity_id: 'e1', value: 'X' }] }, result: { written: 1 } }),
    );
    expect(s).not.toBeNull();
    expect(s!.values).toEqual(['X']);
    expect(s!.written).toBe(1);
    // counts-only (no items) still summarizes — so the call never vanishes.
    expect(summarizeTranslationReview(rec({ result: { written: 0, skipped: 3 } }))).not.toBeNull();
  });
});
