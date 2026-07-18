import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? _k, i18n: { language: 'en' } }),
}));

const drawer = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock('@/features/knowledge/hooks/useDrawerSearch', () => ({
  useDrawerSearch: () => drawer.value,
}));
// The debounce is identity in tests (return the input immediately).
vi.mock('@/features/raw-search/hooks/useDebouncedValue', () => ({
  useDebouncedValue: (v: string) => v,
}));

import { SemanticSearchList } from '../SemanticSearchList';

const HITS = [
  { id: 'h1', project_id: 'p', source_type: 'chapter', source_id: 'ch-9', chunk_index: 0, text: 'the tower fell', is_hub: false, chapter_index: 9, created_at: null, raw_score: 0.91 },
  { id: 'h2', project_id: 'p', source_type: 'glossary', source_id: 'g-1', chunk_index: 0, text: 'a glossary note', is_hub: false, chapter_index: null, created_at: null, raw_score: 0.72 },
];

describe('SemanticSearchList (S-11)', () => {
  beforeEach(() => {
    drawer.value = { hits: [], disabled: false, isFetching: false, error: null };
  });

  it('shows the no-project state when the book has no knowledge project', () => {
    render(<SemanticSearchList projectId={null} isProjectLoading={false} onOpenChapter={vi.fn()} />);
    expect(screen.getByTestId('studio-semantic-no-project')).toBeInTheDocument();
  });

  it('a CHAPTER hit deep-links into the editor at that chapter (source_id)', () => {
    const onOpenChapter = vi.fn();
    drawer.value = { hits: HITS, disabled: false, isFetching: false, error: null };
    render(<SemanticSearchList projectId="p" isProjectLoading={false} initialQuery="tower" onOpenChapter={onOpenChapter} />);
    const hits = screen.getAllByTestId('studio-semantic-hit');
    expect(hits).toHaveLength(2);
    // the chapter-source hit exposes the open-chapter affordance and calls onOpenChapter(source_id)
    fireEvent.click(screen.getByTestId('studio-semantic-open-chapter'));
    expect(onOpenChapter).toHaveBeenCalledWith('ch-9');
  });

  it('a non-chapter hit expands inline instead of deep-linking', () => {
    const onOpenChapter = vi.fn();
    drawer.value = { hits: [HITS[1]], disabled: false, isFetching: false, error: null };
    render(<SemanticSearchList projectId="p" isProjectLoading={false} onOpenChapter={onOpenChapter} />);
    fireEvent.click(screen.getByTestId('studio-semantic-expand'));
    expect(onOpenChapter).not.toHaveBeenCalled();
  });

  it('renders the empty state when there are no hits', () => {
    render(<SemanticSearchList projectId="p" isProjectLoading={false} onOpenChapter={vi.fn()} />);
    expect(screen.getByTestId('studio-semantic-empty')).toBeInTheDocument();
  });
});
