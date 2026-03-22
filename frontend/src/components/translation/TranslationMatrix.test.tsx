import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { TranslationMatrix } from './TranslationMatrix';
import type { Chapter } from '@/features/books/api';
import type { ChapterCoverage } from '@/features/translation/versionsApi';

const BOOK_ID = 'book-1';

const makeChapter = (id: string, sort_order: number, title?: string): Chapter => ({
  chapter_id: id,
  book_id: BOOK_ID,
  title: title ?? `Chapter ${sort_order}`,
  original_filename: `ch${sort_order}.txt`,
  original_language: 'en',
  content_type: 'text/plain',
  byte_size: 1000,
  sort_order,
  lifecycle_state: 'active',
});

const defaultProps = {
  bookId: BOOK_ID,
  chapters: [makeChapter('ch-1', 1), makeChapter('ch-2', 2)],
  coverage: [] as ChapterCoverage[],
  knownLanguages: ['vi', 'zh'],
  selectedIds: [] as string[],
  onToggle: vi.fn(),
  onSelectAll: vi.fn(),
  onDeselectAll: vi.fn(),
};

const renderMatrix = (overrides: Partial<typeof defaultProps> = {}) =>
  render(
    <MemoryRouter>
      <TranslationMatrix {...defaultProps} {...overrides} />
    </MemoryRouter>,
  );

describe('TranslationMatrix — content', () => {
  beforeEach(() => { cleanup(); vi.clearAllMocks(); });

  it('renders a row for each chapter', () => {
    renderMatrix();
    expect(screen.getByText('Chapter 1')).toBeInTheDocument();
    expect(screen.getByText('Chapter 2')).toBeInTheDocument();
  });

  it('renders sort_order in each row', () => {
    renderMatrix();
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('renders language column headers from knownLanguages', () => {
    renderMatrix();
    expect(screen.getByRole('columnheader', { name: 'vi' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'zh' })).toBeInTheDocument();
  });

  it('shows "No chapters found." when chapters array is empty', () => {
    renderMatrix({ chapters: [] });
    expect(screen.getByText('No chapters found.')).toBeInTheDocument();
  });

  it('shows selected count in footer', () => {
    renderMatrix({ selectedIds: ['ch-1', 'ch-2'] });
    expect(screen.getByText('2 selected')).toBeInTheDocument();
  });

  it('shows 0 selected when nothing is selected', () => {
    renderMatrix({ selectedIds: [] });
    expect(screen.getByText('0 selected')).toBeInTheDocument();
  });
});

describe('TranslationMatrix — checkboxes', () => {
  beforeEach(() => { cleanup(); vi.clearAllMocks(); });

  it('chapter checkbox is checked when chapter_id is in selectedIds', () => {
    renderMatrix({ selectedIds: ['ch-1'] });
    const checkboxes = screen.getAllByRole('checkbox');
    // Index 0 = header, 1 = ch-1, 2 = ch-2
    expect(checkboxes[1]).toBeChecked();
    expect(checkboxes[2]).not.toBeChecked();
  });

  it('chapter checkbox is unchecked when chapter is not selected', () => {
    renderMatrix({ selectedIds: [] });
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes[1]).not.toBeChecked();
    expect(checkboxes[2]).not.toBeChecked();
  });

  it('calls onToggle with chapter_id when row checkbox changes', () => {
    const onToggle = vi.fn();
    renderMatrix({ onToggle, selectedIds: [] });
    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[1]);
    expect(onToggle).toHaveBeenCalledWith('ch-1');
  });

  it('header checkbox triggers onSelectAll when not all selected', () => {
    const onSelectAll = vi.fn();
    renderMatrix({ onSelectAll, selectedIds: [] });
    fireEvent.click(screen.getAllByRole('checkbox')[0]);
    expect(onSelectAll).toHaveBeenCalled();
  });

  it('header checkbox triggers onDeselectAll when all chapters are selected', () => {
    const onDeselectAll = vi.fn();
    renderMatrix({ onDeselectAll, selectedIds: ['ch-1', 'ch-2'] });
    fireEvent.click(screen.getAllByRole('checkbox')[0]);
    expect(onDeselectAll).toHaveBeenCalled();
  });

  it('header checkbox is checked when all chapters selected', () => {
    renderMatrix({ selectedIds: ['ch-1', 'ch-2'] });
    expect(screen.getAllByRole('checkbox')[0]).toBeChecked();
  });

  it('header checkbox is unchecked when none selected', () => {
    renderMatrix({ selectedIds: [] });
    expect(screen.getAllByRole('checkbox')[0]).not.toBeChecked();
  });
});

describe('TranslationMatrix — select helpers', () => {
  beforeEach(() => { cleanup(); vi.clearAllMocks(); });

  it('"Select all" button calls onSelectAll', () => {
    const onSelectAll = vi.fn();
    renderMatrix({ onSelectAll });
    fireEvent.click(screen.getByRole('button', { name: 'Select all' }));
    expect(onSelectAll).toHaveBeenCalledOnce();
  });

  it('"Deselect all" button calls onDeselectAll', () => {
    const onDeselectAll = vi.fn();
    renderMatrix({ onDeselectAll });
    fireEvent.click(screen.getByRole('button', { name: 'Deselect all' }));
    expect(onDeselectAll).toHaveBeenCalledOnce();
  });
});

describe('TranslationMatrix — language columns', () => {
  beforeEach(() => { cleanup(); vi.clearAllMocks(); });

  it('renders no language columns when knownLanguages is empty', () => {
    renderMatrix({ knownLanguages: [] });
    expect(screen.queryByRole('columnheader', { name: 'vi' })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: 'zh' })).toBeNull();
  });

  it('renders only filtered language when single language provided', () => {
    renderMatrix({ knownLanguages: ['vi'] });
    expect(screen.getByRole('columnheader', { name: 'vi' })).toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: 'zh' })).toBeNull();
  });
});
