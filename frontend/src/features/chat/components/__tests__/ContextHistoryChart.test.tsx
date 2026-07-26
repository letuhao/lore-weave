import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ContextHistoryPoint } from '../../types';

// W1-residual — the History chart: buildChartData mapping + render states.

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

// Mock recharts so the ResponsiveContainer renders without a real layout in
// jsdom (same pattern as ProgressPanel.test). Bars surface their dataKey so we
// can assert one stack segment per active category.
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  BarChart: ({ children }: any) => <div data-testid="barchart">{children}</div>,
  Bar: ({ dataKey }: any) => <div data-testid={`bar-${dataKey}`} />,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
}));

import { ContextHistoryChart, buildChartData } from '../ContextHistoryChart';

function point(seq: number, breakdown: ContextHistoryPoint['breakdown']): ContextHistoryPoint {
  return { sequence_num: seq, created_at: `t${seq}`, input_tokens: 1000 + seq, output_tokens: 50, breakdown };
}

const POINTS: ContextHistoryPoint[] = [
  point(1, { system_prompt: 100, memory_knowledge: { total: 200, sections: { facts: 200 } }, history: 10 }),
  point(2, { system_prompt: 120, memory_knowledge: { total: 250, sections: { facts: 250 } }, history: 400 }),
];

describe('buildChartData', () => {
  it('maps N turns and flattens memory_knowledge to its total', () => {
    const { data, activeCategories } = buildChartData(POINTS);
    expect(data).toHaveLength(2);
    expect(data[0].turn).toBe(1);
    expect(data[0].memory_knowledge).toBe(200); // nested {total} → number
    expect(data[0].total).toBe(100 + 200 + 10);
    // only categories that are non-zero somewhere, in vocabulary order
    expect(activeCategories).toEqual(['system_prompt', 'memory_knowledge', 'history']);
  });

  it('returns no active categories for an all-zero / empty series', () => {
    expect(buildChartData([]).activeCategories).toEqual([]);
  });
});

describe('ContextHistoryChart', () => {
  it('renders one stacked bar per active category for N turns', () => {
    render(<ContextHistoryChart points={POINTS} loading={false} error={null} />);
    expect(screen.getByTestId('context-history-chart')).toBeInTheDocument();
    expect(screen.getByTestId('bar-system_prompt')).toBeInTheDocument();
    expect(screen.getByTestId('bar-memory_knowledge')).toBeInTheDocument();
    expect(screen.getByTestId('bar-history')).toBeInTheDocument();
    // a category absent from the whole series gets no bar
    expect(screen.queryByTestId('bar-skills')).toBeNull();
    // legend lists the active categories
    expect(screen.getByTestId('context-history-legend')).toBeInTheDocument();
  });

  it('shows the empty state when there are no turns', () => {
    render(<ContextHistoryChart points={[]} loading={false} error={null} />);
    expect(screen.getByTestId('context-history-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('context-history-chart')).toBeNull();
  });

  it('shows the loading spinner before the first load resolves', () => {
    render(<ContextHistoryChart points={[]} loading={true} error={null} />);
    expect(screen.getByTestId('context-history-loading')).toBeInTheDocument();
  });

  it('shows the error state', () => {
    render(<ContextHistoryChart points={[]} loading={false} error="boom" />);
    expect(screen.getByTestId('context-history-error')).toBeInTheDocument();
  });
});
