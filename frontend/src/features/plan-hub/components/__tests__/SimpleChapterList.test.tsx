// Simple mode — the linear list + its CRUD (rename/delete), authorship coding, legend + AI-draft door.
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { SimpleChapterList, type SimpleChapterListProps } from '../SimpleChapterList';
import type { SimpleChapter } from '../../hooks/useSimpleChapters';

function ch(o: Partial<SimpleChapter> & { chapter_id: string }): SimpleChapter {
  return { title: 'Ch', sort_order: 0, word_count: 100, published: false, source: 'authored', ...o };
}

function setup(o: Partial<SimpleChapterListProps> = {}) {
  const props: SimpleChapterListProps = {
    chapters: [ch({ chapter_id: 'c1', title: 'The rounding' })],
    total: 1, loading: false, error: false, hasMore: false,
    loadMore: vi.fn(), loadingMore: false,
    onOpenChapter: vi.fn(), onWriteNew: vi.fn(), writing: false,
    onRename: vi.fn(), onDelete: vi.fn(), mutating: false,
    onAiDraft: vi.fn(), onGoAdvanced: vi.fn(),
    ...o,
  };
  render(<SimpleChapterList {...props} />);
  return props;
}

describe('SimpleChapterList (Simple mode)', () => {
  it('opens a chapter in the editor on row click', () => {
    const { onOpenChapter } = setup();
    fireEvent.click(screen.getByRole('button', { name: 'The rounding' }));
    expect(onOpenChapter).toHaveBeenCalledWith('c1');
  });

  it('the "Write a new chapter" door creates + opens', () => {
    const { onWriteNew } = setup();
    fireEvent.click(screen.getByTestId('plan-hub-simple-write'));
    expect(onWriteNew).toHaveBeenCalled();
  });

  it('RENAME: inline-edits the title and commits on Enter', () => {
    const { onRename } = setup();
    fireEvent.click(screen.getByTestId('plan-hub-simple-edit-c1'));
    const input = screen.getByTestId('plan-hub-simple-rename-c1') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'The rounding — revised' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onRename).toHaveBeenCalledWith('c1', 'The rounding — revised');
  });

  it('RENAME: Escape cancels without a write', () => {
    const { onRename } = setup();
    fireEvent.click(screen.getByTestId('plan-hub-simple-edit-c1'));
    const input = screen.getByTestId('plan-hub-simple-rename-c1');
    fireEvent.change(input, { target: { value: 'nope' } });
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(onRename).not.toHaveBeenCalled();
  });

  it('DELETE: trashes the chapter', () => {
    const { onDelete } = setup();
    fireEvent.click(screen.getByTestId('plan-hub-simple-delete-c1'));
    expect(onDelete).toHaveBeenCalledWith('c1');
  });

  it('an AI (mined) chapter renders mono + carries the mined marker', () => {
    setup({ chapters: [ch({ chapter_id: 'c9', title: "Auger's last clean thought", word_count: null, source: 'mined' })] });
    const row = screen.getByTestId('plan-hub-simple-row-c9');
    expect(row.getAttribute('data-source')).toBe('mined');
    expect(screen.getByRole('button', { name: "Auger's last clean thought" }).className).toContain('font-mono');
  });

  it('shows the authorship+status legend and the AI-draft door link', () => {
    const { onAiDraft } = setup();
    expect(screen.getByTestId('plan-hub-simple-legend')).toBeTruthy();
    fireEvent.click(screen.getByTestId('plan-hub-simple-ai-draft'));
    expect(onAiDraft).toHaveBeenCalled();
  });

  it('CRUD affordances are absent without an EDIT grant (null callbacks)', () => {
    setup({ onRename: null, onDelete: null });
    expect(screen.queryByTestId('plan-hub-simple-edit-c1')).toBeNull();
    expect(screen.queryByTestId('plan-hub-simple-delete-c1')).toBeNull();
  });
});
