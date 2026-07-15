// M1 — the Journal timeline sheet: entries render newest-first, tapping expands the distilled
// prose, kept entries show a badge, and the empty state is honest (not a blank sheet).
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
}));

import { MobileJournalSheet } from '../MobileJournalSheet';
import type { DiaryEntry } from '../../../types';

const entry = (over: Partial<DiaryEntry>): DiaryEntry => ({
  chapter_id: 'c1',
  entry_date: '2026-07-14',
  entry_zone: 'UTC',
  title: 'A good day',
  word_count: 120,
  journal_kind: 'primary',
  kept: false,
  body: 'Line one.\nLine two.',
  ...over,
});

// The sheet only renders its content when ?sheet=journal is active.
function renderOpen(props: Parameters<typeof MobileJournalSheet>[0]) {
  return render(
    <MemoryRouter initialEntries={['/assistant?sheet=journal']}>
      <MobileJournalSheet {...props} />
    </MemoryRouter>,
  );
}

describe('MobileJournalSheet', () => {
  it('renders entries and expands the body on tap', () => {
    renderOpen({ entries: [entry({})], loading: false, error: null });
    const row = screen.getByTestId('journal-entry-c1');
    expect(row.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByTestId('journal-body-c1')).toBeNull();

    fireEvent.click(row);
    expect(screen.getByTestId('journal-entry-c1').getAttribute('aria-expanded')).toBe('true');
    const body = screen.getByTestId('journal-body-c1');
    expect(body.textContent).toContain('Line one.');
    expect(body.textContent).toContain('Line two.');
  });

  it('shows a kept badge for kept entries', () => {
    renderOpen({ entries: [entry({ kept: true })], loading: false, error: null });
    expect(screen.getByLabelText('Kept')).toBeTruthy();
  });

  it('shows an honest empty state (not a blank sheet)', () => {
    renderOpen({ entries: [], loading: false, error: null });
    expect(screen.getByText(/No entries yet/i)).toBeTruthy();
  });

  it('surfaces an error', () => {
    renderOpen({ entries: [], loading: false, error: 'boom' });
    expect(screen.getByText('boom')).toBeTruthy();
  });
});
