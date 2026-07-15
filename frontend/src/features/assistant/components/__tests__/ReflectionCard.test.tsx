import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ReflectionCard } from '../ReflectionCard';
import type { DiaryEntry, ReflectionPattern } from '../../types';

const reflection: DiaryEntry = {
  chapter_id: 'r1', entry_date: '2026-07-12', entry_zone: 'UTC', title: 'Weekly reflection',
  word_count: 20, journal_kind: 'reflection', kept: false,
  body: '## Weekly reflection\n\nA few things stood out this week.',
};

const patterns: ReflectionPattern[] = [
  { detector_code: 'co_occurrence', summary: "'migration' recurred on 2 days", pattern_key: 'co_occurrence:migration' },
  { detector_code: 'journaling_gap', summary: '2 days had no entry', pattern_key: 'journaling_gap' },
];

describe('ReflectionCard', () => {
  it('renders the reflection draft body + the surfaced patterns', () => {
    render(<ReflectionCard reflection={reflection} patterns={patterns} onDismiss={vi.fn()} />);
    expect(screen.getByTestId('reflection-body')).toHaveTextContent('A few things stood out');
    expect(screen.getAllByTestId('reflection-pattern')).toHaveLength(2);
  });

  it('dismissing a pattern calls onDismiss with its period-independent key + hides it', async () => {
    const onDismiss = vi.fn().mockResolvedValue(undefined);
    render(<ReflectionCard reflection={reflection} patterns={patterns} onDismiss={onDismiss} />);
    fireEvent.click(screen.getAllByTestId('dismiss-pattern')[0]);
    await waitFor(() => expect(onDismiss).toHaveBeenCalledWith('co_occurrence:migration'));
    // optimistic hide — the dismissed pattern is removed from view (server is SoT)
    await waitFor(() => expect(screen.getAllByTestId('reflection-pattern')).toHaveLength(1));
  });

  it('a FAILED dismiss keeps the pattern visible + shows a retry error (server is SoT)', async () => {
    const onDismiss = vi.fn().mockRejectedValue(new Error('network'));
    render(<ReflectionCard reflection={reflection} patterns={patterns} onDismiss={onDismiss} />);
    fireEvent.click(screen.getAllByTestId('dismiss-pattern')[0]);
    await waitFor(() => expect(screen.getByTestId('dismiss-error')).toBeInTheDocument());
    // the pattern is NOT hidden on failure (both still visible)
    expect(screen.getAllByTestId('reflection-pattern')).toHaveLength(2);
  });

  it('renders just the draft when there are no patterns (a calm week is valid)', () => {
    render(<ReflectionCard reflection={reflection} patterns={[]} onDismiss={vi.fn()} />);
    expect(screen.getByTestId('reflection-body')).toBeInTheDocument();
    expect(screen.queryByTestId('reflection-patterns')).toBeNull();
  });
});
