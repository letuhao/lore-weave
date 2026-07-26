import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

// MCP fan-out (C-ACTIVITY) — the Tier-A activity / Undo strip: renders each
// streamed op; an available Undo fires onUndo (which the parent wires to the
// named reverse tool). Ops with no reverse render no Undo button.

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? _k }),
}));

import { ActivityStrip } from '../ActivityStrip';
import type { ActivityEvent } from '../../types';

const withUndo: ActivityEvent = {
  op: 'chapter.create',
  summary: "Created draft chapter 'Chapter 5'",
  undo: { available: true, tool: 'chapter_delete', args: { book_id: 'b1', chapter_id: 'ch5' } },
};
const noUndo: ActivityEvent = { op: 'job.start', summary: 'Started translation', undo: { available: false } };

describe('ActivityStrip', () => {
  it('renders one row per activity', () => {
    render(<ActivityStrip activities={[withUndo, noUndo]} onUndo={vi.fn()} />);
    expect(screen.getAllByTestId('activity-row')).toHaveLength(2);
    expect(screen.getByText("Created draft chapter 'Chapter 5'")).toBeInTheDocument();
  });

  it('Undo issues the reverse tool (fires onUndo with the activity)', () => {
    const onUndo = vi.fn();
    render(<ActivityStrip activities={[withUndo]} onUndo={onUndo} />);
    fireEvent.click(screen.getByTestId('activity-undo'));
    expect(onUndo).toHaveBeenCalledWith(withUndo);
  });

  it('does not render an Undo button when no reverse exists', () => {
    render(<ActivityStrip activities={[noUndo]} onUndo={vi.fn()} />);
    expect(screen.queryByTestId('activity-undo')).toBeNull();
  });

  it('a second Undo click on the same row is a no-op', () => {
    const onUndo = vi.fn();
    render(<ActivityStrip activities={[withUndo]} onUndo={onUndo} />);
    const btn = screen.getByTestId('activity-undo');
    fireEvent.click(btn);
    fireEvent.click(btn);
    expect(onUndo).toHaveBeenCalledTimes(1);
  });

  it('renders nothing for an empty list', () => {
    const { container } = render(<ActivityStrip activities={[]} onUndo={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });
});
