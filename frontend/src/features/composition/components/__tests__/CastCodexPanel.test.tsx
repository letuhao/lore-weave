import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CastCodexPanel, groupCast } from '../CastCodexPanel';
import type { Entity, EntityStatusEntry } from '../../../knowledge/api';

const { projHook, castHook, detailHook, eventsHook, factsHook, navigateFn } = vi.hoisted(() => ({
  projHook: vi.fn(), castHook: vi.fn(), detailHook: vi.fn(), eventsHook: vi.fn(), factsHook: vi.fn(), navigateFn: vi.fn(),
}));
vi.mock('../../hooks/useCast', () => ({
  useKnowledgeProjectId: () => projHook(),
  useCast: () => castHook(),
  useEntityDetail: () => detailHook(),
  useEntityEvents: () => eventsHook(),
  useEntityFacts: () => factsHook(),
}));
vi.mock('react-router-dom', () => ({ useNavigate: () => navigateFn }));

function ent(over: Partial<Entity>): Entity {
  return {
    id: 'e', user_id: 'u', project_id: 'p', name: 'X', canonical_name: 'x', kind: 'character',
    aliases: [], canonical_version: 1, source_types: [], confidence: 0.9, glossary_entity_id: null,
    anchor_score: 0, archived_at: null, archive_reason: null, evidence_count: 1, mention_count: 1,
    user_edited: false, version: 1, created_at: null, updated_at: null, ...over,
  };
}

describe('groupCast (T2.1)', () => {
  it('groups by kind (known kinds first), joins status, rows alpha', () => {
    const entities = [
      ent({ id: 'loc1', name: 'The Gate', kind: 'location' }),
      ent({ id: 'c2', name: 'Mira', kind: 'character' }),
      ent({ id: 'c1', name: 'Kael', kind: 'character' }),
    ];
    const statuses: Record<string, EntityStatusEntry> = { c1: { status: 'gone', from_order: 5 } };
    const groups = groupCast(entities, statuses);
    expect(groups.map((g) => g.kind)).toEqual(['character', 'location']); // character before location
    expect(groups[0].rows.map((r) => r.id)).toEqual(['c1', 'c2']); // Kael before Mira
    expect(groups[0].rows[0].state).toEqual({ status: 'gone', from_order: 5 });
    expect(groups[0].rows[1].state).toBeUndefined();
  });

  it('unknown kinds sort after known ones (alpha among unknowns)', () => {
    // s7-4: `organization` is now a KNOWN kind (authorable set); `event_ref` and
    // `zzz` are unknown and sort after it, alpha among themselves.
    const groups = groupCast(
      [ent({ id: 'x', kind: 'zzz' }), ent({ id: 'o', kind: 'organization' }), ent({ id: 'e', kind: 'event_ref' })], {});
    expect(groups.map((g) => g.kind)).toEqual(['organization', 'event_ref', 'zzz']);
  });
});

describe('CastCodexPanel (T2.1)', () => {
  const entities = [
    ent({ id: 'c1', name: 'Kael', kind: 'character', aliases: ['The Oathbreaker'] }),
    ent({ id: 'p1', name: 'The Gate', kind: 'location' }),
  ];

  beforeEach(() => {
    navigateFn.mockReset();
    projHook.mockReturnValue({ data: 'kp1', isLoading: false });
    castHook.mockReturnValue({
      entities: { data: entities, isLoading: false },
      statuses: { data: { statuses: { c1: { status: 'gone', from_order: 5 } }, window_available: true } },
    });
    detailHook.mockReturnValue({ data: { relations: [{ id: 'r1', subject_id: 'c1', predicate: 'mentors', object_name: 'Mira', object_id: 'c2' }], total_relations: 1 } });
    eventsHook.mockReturnValue({ data: [{ id: 'ev1', title: 'The Oath', chapter_id: 'ch1' }] });
    factsHook.mockReturnValue({ data: { facts: [{ id: 'f1', type: 'decision', content: 'broke the oath' }], window_available: true } });
  });

  it('renders the cast grouped by kind with a story-state line', () => {
    render(<CastCodexPanel bookId="b" chapterId="ch3" token="t" />);
    const rows = screen.getAllByTestId('cast-row');
    expect(rows).toHaveLength(2);
    // Kael is gone → row carries data-status=gone (the real derived signal; the
    // global i18n mock returns raw keys so we assert the attribute, not the label).
    const kael = rows.find((r) => r.getAttribute('data-entity') === 'c1')!;
    expect(kael.getAttribute('data-status')).toBe('gone');
    const gate = rows.find((r) => r.getAttribute('data-entity') === 'p1')!;
    expect(gate.getAttribute('data-status')).toBe('active'); // no status → default active
  });

  it('shows the spoiler-window hint when the reading position is unknown', () => {
    castHook.mockReturnValue({
      entities: { data: entities, isLoading: false },
      statuses: { data: { statuses: {}, window_available: false } },
    });
    render(<CastCodexPanel bookId="b" chapterId="ch3" token="t" />);
    expect(screen.getByTestId('cast-window-hint')).toBeInTheDocument();
  });

  it('expands a row to lazy-load relations, events, and known facts', () => {
    render(<CastCodexPanel bookId="b" chapterId="ch3" token="t" />);
    const kael = screen.getAllByTestId('cast-row').find((r) => r.getAttribute('data-entity') === 'c1')!;
    fireEvent.click(kael.querySelector('[data-testid="cast-row-toggle"]')!);
    expect(screen.getByTestId('cast-relation')).toBeInTheDocument();
    expect(screen.getByTestId('cast-fact').textContent).toContain('broke the oath');
    // clicking an event jumps to its chapter.
    fireEvent.click(screen.getByTestId('cast-event'));
    expect(navigateFn).toHaveBeenCalledWith('/books/b/chapters/ch1/edit');
  });

  it('shows the extract-first empty state when there is no knowledge project', () => {
    projHook.mockReturnValue({ data: null, isLoading: false });
    render(<CastCodexPanel bookId="b" chapterId="ch3" token="t" />);
    expect(screen.getByText('codex.noProject')).toBeInTheDocument();
  });

  it('shows the empty state when the project has no extracted entities', () => {
    castHook.mockReturnValue({
      entities: { data: [], isLoading: false },
      statuses: { data: { statuses: {}, window_available: true } },
    });
    render(<CastCodexPanel bookId="b" chapterId="ch3" token="t" />);
    expect(screen.getByText('codex.empty')).toBeInTheDocument();
  });

  // ── D-CAST-KEYSET-PAGING (S7) — Load-more replaces the dead-end truncation ──
  describe('paging', () => {
    it('no Load-more control when the whole cast is loaded (hasMore=false)', () => {
      castHook.mockReturnValue({
        entities: { data: entities, isLoading: false },
        statuses: { data: { statuses: {}, window_available: true } },
        hasMore: false,
      });
      render(<CastCodexPanel bookId="b" chapterId="ch3" token="t" />);
      expect(screen.queryByTestId('cast-load-more')).not.toBeInTheDocument();
    });

    it('renders a Load-more control when more pages remain, and clicking it loads the next page', () => {
      const loadMore = vi.fn();
      castHook.mockReturnValue({
        entities: { data: entities, isLoading: false },
        statuses: { data: { statuses: {}, window_available: true } },
        hasMore: true,
        loadMore,
        isFetchingMore: false,
        loaded: 200,
        total: 250,
      });
      render(<CastCodexPanel bookId="b" chapterId="ch3" token="t" />);
      // A real control, not a dead-end notice.
      const btn = screen.getByTestId('cast-load-more');
      expect(screen.getByTestId('cast-more-hint')).toBeInTheDocument();
      fireEvent.click(btn);
      expect(loadMore).toHaveBeenCalledTimes(1);
    });

    it('disables the control while a page is in flight', () => {
      castHook.mockReturnValue({
        entities: { data: entities, isLoading: false },
        statuses: { data: { statuses: {}, window_available: true } },
        hasMore: true,
        loadMore: vi.fn(),
        isFetchingMore: true,
        loaded: 200,
        total: 250,
      });
      render(<CastCodexPanel bookId="b" chapterId="ch3" token="t" />);
      expect(screen.getByTestId('cast-load-more')).toBeDisabled();
    });
  });
});
