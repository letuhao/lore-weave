import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ProgressPanel } from '../ProgressPanel';
import type { ProgressStats } from '../../types';

// Mock the data hooks so the panel renders deterministically; mock recharts so the
// ResponsiveContainer doesn't need a real layout in jsdom.
const { useProgress, setGoalMutate } = vi.hoisted(() => ({
  useProgress: vi.fn(),
  setGoalMutate: vi.fn(),
}));
vi.mock('../../hooks/useProgress', () => ({
  useProgress,
  useSetDailyGoal: () => ({ mutate: setGoalMutate, isPending: false }),
}));
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  BarChart: ({ children }: any) => <div data-testid="barchart">{children}</div>,
  Bar: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  ReferenceLine: () => <div data-testid="goal-refline" />,
}));

function spark(n: number): ProgressStats['sparkline'] {
  return Array.from({ length: 30 }, (_, i) => ({ date: `2026-06-${String(i + 1).padStart(2, '0')}`, words: i }));
}

function makeData(over: Partial<ProgressStats> = {}): ProgressStats {
  return {
    today: '2026-06-24', today_words: 320, book_total: 5400,
    daily_goal: 500, current_streak: 4, sparkline: spark(30), ...over,
  };
}

describe('ProgressPanel (T4.2)', () => {
  beforeEach(() => { useProgress.mockReset(); setGoalMutate.mockReset(); });

  const renderPanel = () =>
    render(<ProgressPanel bookId="b1" projectId="p1" token="t" />);

  it('shows today words, streak, book total and the goal bar when a goal is set', () => {
    useProgress.mockReturnValue({ data: makeData(), isLoading: false, isError: false });
    renderPanel();
    expect(screen.getByText('320')).toBeInTheDocument();
    expect(screen.getByText('🔥 4')).toBeInTheDocument();
    expect(screen.getByText('5,400')).toBeInTheDocument();
    expect(screen.getByTestId('progress-goal-bar')).toBeInTheDocument();
  });

  it('hides the goal bar and shows the no-goal hint when daily_goal is null', () => {
    useProgress.mockReturnValue({ data: makeData({ daily_goal: null }), isLoading: false, isError: false });
    renderPanel();
    expect(screen.queryByTestId('progress-goal-bar')).not.toBeInTheDocument();
    expect(screen.getByText('progressPanel.noGoal')).toBeInTheDocument();
  });

  it('toggles the sparkline window between 7 and 30 days', () => {
    useProgress.mockReturnValue({ data: makeData(), isLoading: false, isError: false });
    renderPanel();
    // default 7-day is active
    expect(screen.getByTestId('progress-window-7').className).toContain('font-medium');
    fireEvent.click(screen.getByTestId('progress-window-30'));
    expect(screen.getByTestId('progress-window-30').className).toContain('font-medium');
  });

  it('persists an edited goal to the caller own per-user goal (BE-P2 — not shared settings)', () => {
    useProgress.mockReturnValue({ data: makeData(), isLoading: false, isError: false });
    renderPanel();
    fireEvent.change(screen.getByTestId('progress-goal-input'), { target: { value: '750' } });
    fireEvent.click(screen.getByTestId('progress-goal-save'));
    expect(setGoalMutate).toHaveBeenCalledWith(
      { projectId: 'p1', goal: 750 },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it('renders the loading and error states', () => {
    useProgress.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    const { rerender } = renderPanel();
    expect(screen.getByText('progressPanel.loading')).toBeInTheDocument();
    useProgress.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    rerender(<ProgressPanel bookId="b1" projectId="p1" token="t" />);
    expect(screen.getByText('progressPanel.error')).toBeInTheDocument();
  });
});
