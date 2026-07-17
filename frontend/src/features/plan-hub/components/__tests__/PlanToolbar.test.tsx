// 24 PH15 / PH22 / OQ-7 — the Hub toolbar.
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { PlanToolbar } from '../PlanToolbar';

function setup(o: Partial<Parameters<typeof PlanToolbar>[0]> = {}) {
  const props = {
    search: '',
    onSearch: vi.fn(),
    onFit: vi.fn(),
    onProblems: vi.fn(),
    onAskAi: vi.fn(),
    onAddArc: vi.fn(),
    onAddSubArc: vi.fn(),
    creatingArc: false,
    view: 'narrative' as const,
    onView: vi.fn(),
    problemCount: 0,
    ...o,
  };
  render(<PlanToolbar {...props} />);
  return props;
}

describe('PlanToolbar (PH15/PH22)', () => {
  it('PH22 — timeline and worldmap are VISIBLE but DISABLED (P-10: v1 is narrative-only)', () => {
    // The spec is explicit: "buttons visible but disabled". Hiding them would make two capabilities
    // the product intends look like they were never planned; enabling them would be a dead button.
    setup();
    expect((screen.getByTestId('plan-hub-view-narrative') as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByTestId('plan-hub-view-timeline') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId('plan-hub-view-worldmap') as HTMLButtonElement).disabled).toBe(true);
  });

  it('a disabled view mode cannot be selected', () => {
    const { onView } = setup();
    fireEvent.click(screen.getByTestId('plan-hub-view-timeline'));
    expect(onView).not.toHaveBeenCalled();
  });

  it('marks the active mode with aria-pressed', () => {
    setup();
    expect(screen.getByTestId('plan-hub-view-narrative').getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByTestId('plan-hub-view-timeline').getAttribute('aria-pressed')).toBe('false');
  });

  it('fit re-frames the graph', () => {
    const { onFit } = setup();
    fireEvent.click(screen.getByTestId('plan-hub-fit'));
    expect(onFit).toHaveBeenCalled();
  });

  it('the problems button carries the count, and only when there is one', () => {
    setup({ problemCount: 7 });
    expect(screen.getByTestId('plan-hub-problem-count').textContent).toBe('7');
  });

  it('no problems ⇒ no counter (absent, not a green 0)', () => {
    setup({ problemCount: 0 });
    expect(screen.queryByTestId('plan-hub-problem-count')).toBeNull();
  });

  it('OQ-7 — Ask AI is DISABLED with nothing selected (there would be no subject to ask about)', () => {
    setup({ onAskAi: null });
    expect((screen.getByTestId('plan-hub-ask-ai') as HTMLButtonElement).disabled).toBe(true);
  });

  it('Ask AI fires with a selection', () => {
    const onAskAi = vi.fn();
    setup({ onAskAi });
    fireEvent.click(screen.getByTestId('plan-hub-ask-ai'));
    expect(onAskAi).toHaveBeenCalled();
  });

  // Manual structure authoring — the GUI for a backend route (POST /books/{id}/arcs) that had none.
  it('adds a top-level arc', () => {
    const onAddArc = vi.fn();
    setup({ onAddArc });
    fireEvent.click(screen.getByTestId('plan-hub-add-arc'));
    expect(onAddArc).toHaveBeenCalled();
  });

  it('+ Arc is disabled without an EDIT grant (null handler) — visible, never dead (PH7)', () => {
    setup({ onAddArc: null });
    expect((screen.getByTestId('plan-hub-add-arc') as HTMLButtonElement).disabled).toBe(true);
  });

  it('+ Sub-arc is DISABLED unless the selection is an arc (no parent to nest under)', () => {
    setup({ onAddSubArc: null });
    expect((screen.getByTestId('plan-hub-add-subarc') as HTMLButtonElement).disabled).toBe(true);
  });

  it('+ Sub-arc fires when an arc is selected', () => {
    const onAddSubArc = vi.fn();
    setup({ onAddSubArc });
    fireEvent.click(screen.getByTestId('plan-hub-add-subarc'));
    expect(onAddSubArc).toHaveBeenCalled();
  });

  it('both add buttons are disabled mid-create (no double-create)', () => {
    setup({ creatingArc: true });
    expect((screen.getByTestId('plan-hub-add-arc') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId('plan-hub-add-subarc') as HTMLButtonElement).disabled).toBe(true);
  });

  it('typing in find reports the query up (the panel highlights; it never filters)', () => {
    const { onSearch } = setup();
    fireEvent.change(screen.getByTestId('plan-hub-search'), { target: { value: 'summons' } });
    expect(onSearch).toHaveBeenCalledWith('summons');
  });
});
