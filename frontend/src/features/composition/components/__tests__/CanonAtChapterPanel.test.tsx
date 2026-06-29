import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { CanonAtChapter } from '../../hooks/useCanonAtChapter';

const h = vi.hoisted(() => ({ state: {} as CanonAtChapter }));
vi.mock('../../hooks/useCanonAtChapter', () => ({ useCanonAtChapter: () => h.state }));

import { CanonAtChapterPanel } from '../CanonAtChapterPanel';

const base = { bookId: 'b', chapterId: 'c1', token: 't', enabled: true };

describe('CanonAtChapterPanel (M6)', () => {
  it('no chapter in focus → prompt (no fetch)', () => {
    render(<CanonAtChapterPanel {...base} chapterId={null} />);
    expect(screen.getByTestId('canonview-empty')).toBeTruthy();
  });

  it('loading state', () => {
    h.state = { present: [], established: null, canonState: null, timeline: null, knowledgeError: false, isLoading: true, isEmpty: false };
    render(<CanonAtChapterPanel {...base} />);
    expect(screen.getByTestId('canonview-loading')).toBeTruthy();
  });

  it('not-analyzed when every windowed source is empty', () => {
    h.state = {
      present: [], established: [], canonState: { active: 0, gone: 0, windowAvailable: true },
      timeline: { events: 0 }, knowledgeError: false, isLoading: false, isEmpty: true,
    };
    render(<CanonAtChapterPanel {...base} />);
    expect(screen.getByTestId('canonview-not-analyzed')).toBeTruthy();
  });

  it('knowledge fetch error → "canon state unavailable" (not a silent empty)', () => {
    h.state = {
      present: [{ entity_id: 'e1', name: 'Alice', kind_code: 'character', relevance: 'major', chapter_index: 0, mention_count: 0 }],
      established: null, canonState: null, timeline: null, knowledgeError: true, isLoading: false, isEmpty: false,
    };
    render(<CanonAtChapterPanel {...base} />);
    expect(screen.getByTestId('canonview-knowledge-error')).toBeTruthy();
  });

  it('renders glossary presence + established + knowledge canon-state, labeled by source', () => {
    h.state = {
      present: [{ entity_id: 'e1', name: 'Alice', kind_code: 'character', relevance: 'major', chapter_index: 0, mention_count: 3 }],
      established: [{ entity_id: 'e1', name: 'Alice', kind_code: 'character', aliases: [], frequency: 3, first_chapter_index: 0, last_chapter_index: 2, coverage_pct: 0.5 }],
      canonState: { active: 5, gone: 1, windowAvailable: true },
      timeline: { events: 4 },
      knowledgeError: false, isLoading: false, isEmpty: false,
    };
    render(<CanonAtChapterPanel {...base} chapterIndex={0} />);
    const presence = screen.getByTestId('canonview-presence');
    expect(within(presence).getByText('Alice')).toBeTruthy();
    expect(within(presence).getByText('×3')).toBeTruthy();        // mention_count badge
    expect(within(presence).getByText('canonview.srcGlossary')).toBeTruthy();
    expect(screen.getByTestId('canonview-established')).toBeTruthy();
    const state = screen.getByTestId('canonview-canonstate');
    expect(within(state).getByText('canonview.srcKnowledge')).toBeTruthy();
    // the i18n test mock returns the key (defaultValue ignored), so assert the keys
    expect(within(state).getByText('canonview.active')).toBeTruthy();
    expect(within(state).getByText('canonview.events')).toBeTruthy();
  });

  it('knowledge window unavailable → fail-closed hint (not a clean-slate)', () => {
    h.state = {
      present: [{ entity_id: 'e1', name: 'Bob', kind_code: 'character', relevance: 'appears', chapter_index: 1, mention_count: 0 }],
      established: null, canonState: { active: 0, gone: 0, windowAvailable: false }, timeline: null,
      knowledgeError: false, isLoading: false, isEmpty: false,
    };
    render(<CanonAtChapterPanel {...base} />);
    expect(screen.getByText('canonview.windowUnavailable')).toBeTruthy();
    // established section omitted when chapterIndex absent (established === null)
    expect(screen.queryByTestId('canonview-established')).toBeNull();
  });
});
