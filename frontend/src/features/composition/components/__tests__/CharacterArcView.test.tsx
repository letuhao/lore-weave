import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CharacterArcView } from '../CharacterArcView';
import { arcBandSplit } from '../../hooks/useCharacterArc';
import type { EntityRelation, TimelineEvent } from '../../../knowledge/api';

// Keep the REAL pure arcBandSplit; override only the hook + navigate.
const { hook } = vi.hoisted(() => ({ hook: vi.fn() }));
vi.mock('../../hooks/useCharacterArc', async (orig) => ({
  ...(await orig<typeof import('../../hooks/useCharacterArc')>()),
  useCharacterArc: () => hook(),
}));
const { navigate } = vi.hoisted(() => ({ navigate: vi.fn() }));
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }));

// D-KG-EVENT-CREATE-ROUTE — stub the create dialog (its hooks need auth + a
// QueryClient this leaf test doesn't provide). We assert it opens with the
// right create context.
const { dialog } = vi.hoisted(() => ({ dialog: vi.fn() }));
vi.mock('@/features/knowledge/components/EventEditDialog', () => ({
  EventEditDialog: (p: { open: boolean; create?: { projectId: string; participants?: string[] } }) => {
    dialog(p);
    return p.open ? <div data-testid="event-create-dialog" data-project={p.create?.projectId} data-participant={p.create?.participants?.[0]} /> : null;
  },
}));

function ev(id: string, order: number): TimelineEvent {
  return {
    id, user_id: 'u', project_id: 'kp1', title: id, canonical_title: id, summary: id,
    chapter_id: 'c-' + id, chapter_title: 'Ch ' + id, event_order: order, chronological_order: order,
    event_date_iso: null, time_cue: null, participants: [], confidence: 0.9, source_types: [],
    evidence_count: 1, mention_count: 1, archived_at: null, version: 1, created_at: null, updated_at: null,
  };
}
function rel(over: Partial<EntityRelation>): EntityRelation {
  return {
    id: 'r1', subject_id: 'kael', object_id: 'mira', predicate: 'ally', confidence: 0.9,
    source_event_ids: [], source_chapter: null, valid_from: null, valid_until: null,
    pending_validation: false, created_at: null, updated_at: null,
    subject_name: 'Kael', subject_kind: 'character', object_name: 'Mira', object_kind: 'character', ...over,
  };
}

describe('arcBandSplit (T2.4)', () => {
  const evs = [ev('e1', 1), ev('e2', 4), ev('e3', 7)];
  it('returns count while active (no gone band)', () => {
    expect(arcBandSplit(evs, 'active', null)).toBe(3);
    expect(arcBandSplit(evs, undefined, 5)).toBe(3);
  });
  it('splits at the first event past the gone-transition order', () => {
    expect(arcBandSplit(evs, 'gone', 5)).toBe(2); // e3 (order 7) is first ≥ 5
    expect(arcBandSplit(evs, 'gone', 1)).toBe(0); // all gone from the start
  });
  it('gone with no transition order → whole arc gone (0); gone past all events → count', () => {
    expect(arcBandSplit(evs, 'gone', null)).toBe(0);
    expect(arcBandSplit(evs, 'gone', 99)).toBe(3);
  });
});

describe('CharacterArcView (T2.4)', () => {
  const onEntityChange = vi.fn();
  const base = {
    projectId: 'kp1', projectLoading: false,
    roster: [{ id: 'kael', name: 'Kael' }, { id: 'mira', name: 'Mira' }],
    effectiveEntityId: 'kael',
    events: [ev('e1', 1), ev('e2', 4), ev('e3', 7)],
    visibleCount: 2,
    relations: [rel({ id: 'r1', predicate: 'ally' })],
    state: { status: 'gone' as const, from_order: 5 },
    isLoading: false,
  };
  const render0 = () =>
    render(<CharacterArcView bookId="b" chapterId="ch" token="t" entityId="kael" onEntityChange={onEntityChange} />);
  const eventEl = (id: string) =>
    screen.getAllByTestId('timeline-event').find((g) => g.getAttribute('data-event-id') === id)!;

  beforeEach(() => { onEntityChange.mockReset(); navigate.mockReset(); dialog.mockReset(); hook.mockReturnValue(base); });

  it('renders the arc events with the spoiler cut and dims the future', () => {
    render0();
    expect(screen.getAllByTestId('timeline-event')).toHaveLength(3);
    expect(eventEl('e2').getAttribute('data-hidden')).toBe('false');
    expect(eventEl('e3').getAttribute('data-hidden')).toBe('true'); // visibleCount=2
    expect(screen.getByTestId('timeline-cut')).toBeInTheDocument();
  });

  it('renders the active→gone band when the character is gone', () => {
    render0();
    expect(screen.getByTestId('arc-band-active')).toBeInTheDocument();
    expect(screen.getByTestId('arc-band-gone')).toBeInTheDocument();
    expect(screen.getByTestId('arc-state-badge').getAttribute('data-status')).toBe('gone');
  });

  it('omits the gone band for an active character', () => {
    hook.mockReturnValue({ ...base, state: { status: 'active', from_order: null } });
    render0();
    expect(screen.getByTestId('arc-band-active')).toBeInTheDocument();
    expect(screen.queryByTestId('arc-band-gone')).not.toBeInTheDocument();
  });

  it('renders the current relations strip (direction-aware)', () => {
    render0();
    const chips = screen.getAllByTestId('arc-relation');
    expect(chips).toHaveLength(1);
    expect(chips[0].textContent).toContain('Mira'); // kael --ally--> Mira
  });

  it('switching the character calls onEntityChange', () => {
    render0();
    fireEvent.change(screen.getByTestId('arc-character-select'), { target: { value: 'mira' } });
    expect(onEntityChange).toHaveBeenCalledWith('mira');
  });

  it('clicking an event opens its chapter', () => {
    render0();
    fireEvent.click(eventEl('e2'));
    expect(navigate).toHaveBeenCalledWith('/books/b/chapters/c-e2/edit');
  });

  it('shows an empty hint when the character has no events', () => {
    hook.mockReturnValue({ ...base, events: [], visibleCount: 0 });
    render0();
    expect(screen.getByTestId('arc-empty')).toBeInTheDocument();
  });

  it('shows the extract-first state with no knowledge project', () => {
    hook.mockReturnValue({ ...base, projectId: null, roster: [], events: [] });
    render0();
    expect(screen.getByText('chararc.noProject')).toBeInTheDocument();
  });

  // D-KG-EVENT-CREATE-ROUTE — the "+ Add event" affordance.
  it('opens the create dialog anchored to this character on + Add event', () => {
    render0();
    // Closed until clicked.
    expect(screen.queryByTestId('event-create-dialog')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('arc-add-event'));
    const dlg = screen.getByTestId('event-create-dialog');
    expect(dlg.getAttribute('data-project')).toBe('kp1');
    expect(dlg.getAttribute('data-participant')).toBe('Kael'); // focused character anchors the event
  });

  it('hides + Add event without a knowledge project (nothing to author into)', () => {
    hook.mockReturnValue({ ...base, projectId: null });
    render0();
    expect(screen.queryByTestId('arc-add-event')).not.toBeInTheDocument();
  });
});
