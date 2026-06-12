import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));
vi.mock('@/components/reader/ContentRenderer', () => ({
  ContentRenderer: ({ blocks }: { blocks: unknown[] }) => (
    <div data-testid="content-renderer">{blocks.length} blocks</div>
  ),
}));
vi.mock('@/components/reader/CitationContext', () => ({
  CitationProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

import { WikiSuggestionReview } from '../WikiSuggestionReview';
import type { WikiSuggestionResp } from '../../types';

const doc = (lines: string[]) => ({
  type: 'doc',
  content: lines.map((l) => ({ type: 'paragraph', content: [{ type: 'text', text: l }] })),
});

const aiSug: WikiSuggestionResp = {
  suggestion_id: 's1',
  article_id: 'a1',
  user_id: 'u1',
  diff_json: { body_json: doc(['lead kept', 'new sentence']), generation_status: 'generated' },
  reason: 'regenerated',
  status: 'pending',
  reviewer_note: null,
  created_at: '',
  reviewed_at: null,
  article_display_name: 'Mina',
};

describe('WikiSuggestionReview', () => {
  it('renders the AI-regen badge + a preview, and hides the diff until toggled', () => {
    render(
      <WikiSuggestionReview
        suggestion={aiSug}
        currentBodyJson={doc(['lead kept', 'old sentence'])}
        bookId="b1"
        onAccept={() => {}}
        onReject={() => {}}
      />,
    );
    expect(screen.getByText('suggestions.aiRegen')).toBeTruthy();
    expect(screen.getByTestId('content-renderer')).toBeTruthy(); // preview rendered
    // diff is collapsed → the changed lines aren't in the DOM yet (preview is mocked)
    expect(screen.queryByText('new sentence')).toBeNull();
    fireEvent.click(screen.getByText('suggestions.showDiff'));
    expect(screen.getByText('new sentence')).toBeTruthy(); // add row
    expect(screen.getByText('old sentence')).toBeTruthy(); // del row
  });

  it('fires onAccept / onReject', () => {
    const onAccept = vi.fn();
    const onReject = vi.fn();
    render(
      <WikiSuggestionReview suggestion={aiSug} bookId="b1" onAccept={onAccept} onReject={onReject} />,
    );
    fireEvent.click(screen.getByText('suggestions.accept'));
    fireEvent.click(screen.getByText('suggestions.reject'));
    expect(onAccept).toHaveBeenCalledOnce();
    expect(onReject).toHaveBeenCalledOnce();
  });

  it('omits the diff toggle when no current body is provided', () => {
    render(<WikiSuggestionReview suggestion={aiSug} bookId="b1" onAccept={() => {}} onReject={() => {}} />);
    expect(screen.queryByText('suggestions.showDiff')).toBeNull();
  });

  it('degrades a non-envelope diff_json to a community fallback (no crash, no diff)', () => {
    const community: WikiSuggestionResp = { ...aiSug, diff_json: { before: 'x', after: 'y' } };
    render(
      <WikiSuggestionReview
        suggestion={community}
        currentBodyJson={doc(['a'])}
        bookId="b1"
        onAccept={() => {}}
        onReject={() => {}}
      />,
    );
    expect(screen.getByText('suggestions.community')).toBeTruthy();
    expect(screen.queryByText('suggestions.showDiff')).toBeNull();
    expect(screen.queryByTestId('content-renderer')).toBeNull();
  });
});
