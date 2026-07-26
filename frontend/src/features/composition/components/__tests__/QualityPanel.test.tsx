import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QualityPanel } from '../QualityPanel';
import type { ModeCorrectionStats } from '../../types';

const { mockStats } = vi.hoisted(() => ({
  mockStats: { isLoading: false, isError: false, data: undefined as unknown },
}));
vi.mock('../../hooks/useCorrectionStats', () => ({ useCorrectionStats: () => mockStats }));

function mode(over: Partial<ModeCorrectionStats> & { mode: string }): ModeCorrectionStats {
  return {
    generations: 0, corrected_jobs: 0, accept_rate: null, edit_rate: null,
    pick_different_rate: null, regenerate_rate: null, reject_rate: null,
    avg_edit_magnitude: null, ...over,
  };
}

beforeEach(() => {
  mockStats.isLoading = false;
  mockStats.isError = false;
  mockStats.data = undefined;
});

describe('QualityPanel (eval-gate dashboard — slice 5)', () => {
  it('shows the cold-start hint when there are no generations', () => {
    mockStats.data = { project_id: 'p', by_mode: [mode({ mode: 'auto' }), mode({ mode: 'cowrite' })] };
    render(<QualityPanel projectId="p" token="t" modelRef="m" />);
    expect(screen.getByTestId('composition-quality-coldstart')).toBeTruthy();
  });

  it('renders per-mode rates as a within-author A/B once generations exist', () => {
    mockStats.data = { project_id: 'p', by_mode: [
      mode({ mode: 'auto', generations: 4, corrected_jobs: 2, accept_rate: 0.5,
             edit_rate: 0.25, pick_different_rate: 0.25, regenerate_rate: 0, reject_rate: 0,
             avg_edit_magnitude: 3 }),
      mode({ mode: 'cowrite', generations: 2, corrected_jobs: 1, accept_rate: 0.5,
             edit_rate: 0, pick_different_rate: 0, regenerate_rate: 0.5, reject_rate: 0 }),
    ] };
    render(<QualityPanel projectId="p" token="t" modelRef="m" />);
    expect(screen.queryByTestId('composition-quality-coldstart')).toBeNull();
    const autoCells = screen.getAllByTestId('stat-auto').map((c) => c.textContent);
    expect(autoCells).toContain('50%'); // accept_rate
    expect(autoCells).toContain('25%'); // edit_rate
    expect(autoCells).toContain('3.0'); // avg edit magnitude
    const cowCells = screen.getAllByTestId('stat-cowrite').map((c) => c.textContent);
    expect(cowCells).toContain('—'); // null avg_edit_magnitude renders as em dash
  });

  it('shows an error state when the query fails', () => {
    mockStats.isError = true;
    render(<QualityPanel projectId="p" token="t" modelRef="m" />);
    expect(screen.getByText('statsUnavailable')).toBeTruthy();
  });
});
