import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

// WikiGenBadge (rendered per row) pulls its own useTranslation — interpolating stub.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, o?: Record<string, unknown>) => (o ? `${k}:${JSON.stringify(o)}` : k),
  }),
}));

import { WikiSidebar } from '../WikiTab';
import type { WikiArticleListItem, WikiGenerationStatus } from '@/features/wiki/types';

const tStub = (k: string, o?: Record<string, unknown>) => (o ? `${k}:${JSON.stringify(o)}` : k);

const kind = { code: 'character', name: 'Character', icon: '🧍', color: '#abc' };

function article(id: string, gen: WikiGenerationStatus | null): WikiArticleListItem {
  return {
    article_id: id,
    entity_id: `e-${id}`,
    book_id: 'b1',
    display_name: `Article ${id}`,
    kind,
    status: 'published',
    template_code: null,
    revision_count: 1,
    updated_at: '2026-06-11T00:00:00Z',
    generation_status: gen,
  };
}

function renderSidebar(articles: WikiArticleListItem[]) {
  return render(
    <WikiSidebar
      articles={articles}
      selectedId={null}
      onSelect={() => {}}
      kinds={[kind]}
      kindFilter=""
      onKindFilter={() => {}}
      search=""
      onSearch={() => {}}
      t={tStub}
    />,
  );
}

describe('WikiSidebar — AI-count split (W3)', () => {
  it('shows "N articles · M by AI" counting generation_status within the loaded list', () => {
    renderSidebar([article('1', 'generated'), article('2', 'needs_review'), article('3', null)]);
    // N = loaded list length (3); M = AI-authored (2 of 3 have a generation_status).
    // Both render in one span, so match the combined text by substring.
    expect(screen.getByText(/articles:\{"count":3\}/)).toBeTruthy();
    expect(screen.getByText(/aiSplit:\{"count":2\}/)).toBeTruthy();
  });

  it('omits the AI split when no article is AI-authored', () => {
    renderSidebar([article('1', null), article('2', null)]);
    expect(screen.getByText('articles:{"count":2}')).toBeTruthy();
    expect(screen.queryByText(/aiSplit/)).toBeNull();
  });
});
