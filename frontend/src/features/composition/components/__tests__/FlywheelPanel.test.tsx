import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FlywheelPanel } from '../FlywheelPanel';
import type { FlywheelDeltaWire } from '@/features/knowledge/api';

const { mockFly } = vi.hoisted(() => ({ mockFly: { data: undefined as unknown, isLoading: false, isError: false } }));
vi.mock('../../hooks/useFlywheel', () => ({ useFlywheel: () => mockFly }));

function delta(over: Partial<FlywheelDeltaWire> = {}): FlywheelDeltaWire {
  return {
    has_delta: true, job_id: 'j1', completed_at: null,
    entities_added: 4, relations_added: 2, events_added: 1, new_items: [], ...over,
  };
}

function setup() {
  const props = { projectId: 'p1', token: 't', onOpenCast: vi.fn(), onOpenTimeline: vi.fn(), onOpenRelations: vi.fn() };
  render(<FlywheelPanel {...props} />);
  return props;
}

beforeEach(() => { mockFly.data = undefined; mockFly.isLoading = false; mockFly.isError = false; });

describe('FlywheelPanel (T4.1)', () => {
  it('shows the neutral empty state when no extraction has completed', () => {
    mockFly.data = { has_delta: false, job_id: null, completed_at: null, entities_added: 0, relations_added: 0, events_added: 0, new_items: [] };
    setup();
    expect(screen.getByTestId('flywheel-empty')).toBeTruthy();
    expect(screen.queryByTestId('flywheel-panel')).toBeNull();
  });

  it('shows empty state when has_delta but all counts are zero', () => {
    mockFly.data = delta({ entities_added: 0, relations_added: 0, events_added: 0 });
    setup();
    expect(screen.getByTestId('flywheel-empty')).toBeTruthy();
  });

  it('renders the +N stats when there is a delta', () => {
    mockFly.data = delta();
    setup();
    expect(screen.getByTestId('flywheel-panel')).toBeTruthy();
    expect(screen.getByTestId('flywheel-stat-entities').textContent).toContain('+4');
    expect(screen.getByTestId('flywheel-stat-relations').textContent).toContain('+2');
    expect(screen.getByTestId('flywheel-stat-events').textContent).toContain('+1');
  });

  it('stat buttons deep-link to their views', () => {
    mockFly.data = delta();
    const props = setup();
    fireEvent.click(screen.getByTestId('flywheel-stat-entities'));
    expect(props.onOpenCast).toHaveBeenCalledWith(); // no name → just open Cast
    fireEvent.click(screen.getByTestId('flywheel-stat-relations'));
    expect(props.onOpenRelations).toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('flywheel-stat-events'));
    expect(props.onOpenTimeline).toHaveBeenCalled();
  });

  it('chips deep-link to the specific item by kind (entity → Cast focused by name)', () => {
    mockFly.data = delta({
      new_items: [
        { kind: 'entity', id: 'e1', name: 'Kael' },
        { kind: 'event', id: 'v1', name: 'The Duel' },
        { kind: 'relation', id: 'r1', name: 'Kael → ALLY_OF → Mira' },
      ],
    });
    const props = setup();
    fireEvent.click(screen.getByTestId('flywheel-chip-e1'));
    expect(props.onOpenCast).toHaveBeenCalledWith('Kael'); // focuses the entity
    fireEvent.click(screen.getByTestId('flywheel-chip-v1'));
    expect(props.onOpenTimeline).toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('flywheel-chip-r1'));
    expect(props.onOpenRelations).toHaveBeenCalled();
  });

  it('a disabled (zero) stat does not deep-link', () => {
    mockFly.data = delta({ events_added: 0 });
    const props = setup();
    fireEvent.click(screen.getByTestId('flywheel-stat-events'));
    expect(props.onOpenTimeline).not.toHaveBeenCalled();
  });
});
