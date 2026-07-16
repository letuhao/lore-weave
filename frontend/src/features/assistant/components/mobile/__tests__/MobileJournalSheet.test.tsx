// M1 — the Journal timeline sheet: entries render newest-first, tapping expands the distilled
// prose, kept entries show a badge, and the empty state is honest (not a blank sheet).
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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

  // DF7 / D17 — the pencil opens an inline editor; Save calls onCorrect with the edited body; a
  // successful amend closes the editor; the no-share note is present (never published/shared).
  it('corrects an entry: pencil → edit → save calls onCorrect and closes on success', async () => {
    const onCorrect = vi.fn().mockResolvedValue({ amended: true });
    renderOpen({ entries: [entry({})], loading: false, error: null, onCorrect, correctingId: null });

    fireEvent.click(screen.getByTestId('journal-entry-c1')); // expand
    fireEvent.click(screen.getByTestId('journal-correct-c1')); // open editor
    const editor = screen.getByTestId('journal-editor-c1') as HTMLTextAreaElement;
    expect(editor.value).toContain('Line one.'); // seeded with the current body
    expect(screen.getByText(/Never shared/i)).toBeTruthy();

    fireEvent.change(editor, { target: { value: 'Corrected line.' } });
    fireEvent.click(screen.getByTestId('journal-save-c1'));
    expect(onCorrect).toHaveBeenCalledWith('c1', 'Corrected line.', 'A good day');
    await waitFor(() => expect(screen.queryByTestId('journal-editor-c1')).toBeNull()); // closed after amend:true
  });

  it('keeps the editor OPEN when the correction fails (onCorrect returns null)', async () => {
    const onCorrect = vi.fn().mockResolvedValue(null);
    renderOpen({ entries: [entry({})], loading: false, error: null, onCorrect, correctingId: null });
    fireEvent.click(screen.getByTestId('journal-entry-c1'));
    fireEvent.click(screen.getByTestId('journal-correct-c1'));
    fireEvent.click(screen.getByTestId('journal-save-c1'));
    await Promise.resolve();
    expect(screen.getByTestId('journal-editor-c1')).toBeTruthy(); // still editable to retry
  });

  it('hides the correct affordance when no onCorrect handler is wired', () => {
    renderOpen({ entries: [entry({})], loading: false, error: null });
    fireEvent.click(screen.getByTestId('journal-entry-c1'));
    expect(screen.queryByTestId('journal-correct-c1')).toBeNull();
  });
});
