import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { Entity } from '../../api';

const useEntitiesMock = vi.fn();
vi.mock('../../hooks/useEntities', () => ({
  useEntities: (...args: unknown[]) => useEntitiesMock(...args),
}));

import { TimelineFilters } from '../TimelineFilters';

const ENTITY_KAI: Entity = {
  id: 'ent-kai',
  user_id: 'u1',
  project_id: 'p-1',
  name: 'Kai',
  canonical_name: 'kai',
  kind: 'character',
  aliases: ['Master Kai'],
  canonical_version: 1,
  source_types: ['chapter'],
  confidence: 0.9,
  glossary_entity_id: null,
  anchor_score: 0,
  archived_at: null,
  archive_reason: null,
  evidence_count: 0,
  mention_count: 0,
  user_edited: false,
  version: 1,
  created_at: null,
  updated_at: null,
};

function defaultProps(overrides = {}) {
  return {
    projectId: undefined as string | undefined,
    entity: null as Entity | null,
    onEntityChange: vi.fn(),
    afterChronological: null as number | null,
    beforeChronological: null as number | null,
    onChronologicalRangeChange: vi.fn(),
    ...overrides,
  };
}

describe('TimelineFilters', () => {
  beforeEach(() => {
    useEntitiesMock.mockReset();
    useEntitiesMock.mockReturnValue({
      entities: [],
      total: 0,
      isLoading: false,
      isFetching: false,
      error: null,
    });
    // Real timers: the 250ms debounce is cheap and waitFor composes
    // with it predictably. Fake timers collide with testing-library's
    // internal setTimeout-based polling.
  });

  it('renders entity input + chronological range inputs', () => {
    render(<TimelineFilters {...defaultProps()} />);
    expect(
      screen.getByTestId('timeline-filter-entity-input'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('timeline-filter-chrono-after'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('timeline-filter-chrono-before'),
    ).toBeInTheDocument();
  });

  it('typing ≥2 chars opens the entity dropdown with search results', async () => {
    useEntitiesMock.mockReturnValue({
      entities: [ENTITY_KAI],
      total: 1,
      isLoading: false,
      isFetching: false,
      error: null,
    });
    const onEntityChange = vi.fn();
    render(
      <TimelineFilters {...defaultProps({ onEntityChange })} />,
    );
    const input = screen.getByTestId('timeline-filter-entity-input');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'Ka' } });
    // Debounce 250ms — waitFor polls until the dropdown appears.
    await waitFor(
      () => {
        expect(
          screen.getByTestId('timeline-filter-entity-dropdown'),
        ).toBeInTheDocument();
      },
      { timeout: 1500 },
    );
    fireEvent.click(
      screen.getByTestId(`timeline-filter-entity-option-${ENTITY_KAI.id}`),
    );
    expect(onEntityChange).toHaveBeenCalledWith(ENTITY_KAI);
  });

  it('renders the entity chip and X-button when entity prop is set', () => {
    const onEntityChange = vi.fn();
    render(
      <TimelineFilters
        {...defaultProps({ entity: ENTITY_KAI, onEntityChange })}
      />,
    );
    expect(
      screen.getByTestId('timeline-filter-entity-selected'),
    ).toHaveTextContent('Kai');
    fireEvent.click(screen.getByTestId('timeline-filter-entity-clear'));
    expect(onEntityChange).toHaveBeenCalledWith(null);
  });

  it('typing in chronological inputs debounces the commit to onChronologicalRangeChange', async () => {
    // C10 /review-impl [MED#1]: rapid keystrokes coalesce into a
    // single debounced callback so BE isn't hit once per keystroke.
    const onChronologicalRangeChange = vi.fn();
    render(
      <TimelineFilters
        {...defaultProps({ onChronologicalRangeChange })}
      />,
    );
    const input = screen.getByTestId('timeline-filter-chrono-after');
    fireEvent.change(input, { target: { value: '1' } });
    fireEvent.change(input, { target: { value: '15' } });
    fireEvent.change(input, { target: { value: '150' } });
    fireEvent.change(input, { target: { value: '1500' } });
    // No synchronous callback — the last value is committed after
    // the 400ms debounce window.
    expect(onChronologicalRangeChange).not.toHaveBeenCalled();
    await waitFor(
      () => {
        expect(onChronologicalRangeChange).toHaveBeenCalled();
      },
      { timeout: 1500 },
    );
    // Only ONE commit survives — 4 keystrokes batched.
    expect(onChronologicalRangeChange).toHaveBeenCalledTimes(1);
    expect(onChronologicalRangeChange).toHaveBeenLastCalledWith(1500, null);
  });

  it('parent resets propagate to inputs without re-firing onChronologicalRangeChange', async () => {
    // /review-impl [MED#1] companion: if the parent resets props to
    // null (e.g., project change), the inputs clear without emitting
    // a stale commit back.
    const onChronologicalRangeChange = vi.fn();
    const { rerender } = render(
      <TimelineFilters
        {...defaultProps({
          afterChronological: 50,
          onChronologicalRangeChange,
        })}
      />,
    );
    expect(
      (screen.getByTestId('timeline-filter-chrono-after') as HTMLInputElement)
        .value,
    ).toBe('50');
    rerender(
      <TimelineFilters
        {...defaultProps({
          afterChronological: null,
          onChronologicalRangeChange,
        })}
      />,
    );
    expect(
      (screen.getByTestId('timeline-filter-chrono-after') as HTMLInputElement)
        .value,
    ).toBe('');
    // Props now match the local state after the sync effect; the
    // debounced commit effect's no-change guard skips the callback.
    await new Promise((r) => setTimeout(r, 500));
    expect(onChronologicalRangeChange).not.toHaveBeenCalled();
  });

  it('shows the reversed-range hint when after ≥ before', () => {
    render(
      <TimelineFilters
        {...defaultProps({
          afterChronological: 50,
          beforeChronological: 10,
        })}
      />,
    );
    expect(
      screen.getByTestId('timeline-filter-chrono-reversed'),
    ).toBeInTheDocument();
  });

  it('scopes entity search to the current projectId', async () => {
    useEntitiesMock.mockReturnValue({
      entities: [],
      total: 0,
      isLoading: false,
      isFetching: false,
      error: null,
    });
    render(
      <TimelineFilters
        {...defaultProps({ projectId: 'p-1' })}
      />,
    );
    const input = screen.getByTestId('timeline-filter-entity-input');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'Kai' } });
    // useEntities was called with project_id=p-1 + search=Kai after
    // the 250ms debounce elapses.
    await waitFor(
      () => {
        const calls = useEntitiesMock.mock.calls;
        expect(calls.length).toBeGreaterThan(0);
        const lastCall = calls[calls.length - 1][0];
        expect(lastCall.project_id).toBe('p-1');
        expect(lastCall.search).toBe('Kai');
      },
      { timeout: 1500 },
    );
  });
});
