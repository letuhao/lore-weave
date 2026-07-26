import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useRef, useState } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

// Fixed candidate data — the real fetching lives in useContextCandidates (mocked here).
const candidatesFixture = {
  books: [
    { book_id: 'b1', title: 'Thư Sơn' },
    { book_id: 'b2', title: 'Other Book' },
  ],
  chapters: [
    { chapter_id: 'c1', book_id: 'b1', title: 'Chapter One', original_filename: '', bookTitle: 'Thư Sơn' },
  ],
  entities: [
    { entity_id: 'e1', book_id: 'b1', display_name: 'Lâm Tuyệt', kind: { name: 'Character', color: '#f00' } },
    { entity_id: 'e2', book_id: 'b1', display_name: 'Hồ Lâm', kind: { name: 'Character', color: '#0f0' } },
  ],
};
const useContextCandidatesMock = vi.fn((_opts: unknown) => candidatesFixture);
vi.mock('../useContextCandidates', () => ({
  useContextCandidates: (opts: unknown) => useContextCandidatesMock(opts),
}));

import { useMentionPicker } from '../useMentionPicker';
import { MentionPopover } from '../../components/MentionPopover';
import type { ContextItem } from '../../context/types';

const onAttach = vi.fn();
const onSend = vi.fn();

/** Minimal stand-in for the ChatInputBar wiring (value state + textarea + popover). */
function Harness() {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mention = useMentionPicker({
    value,
    onAttach: (item: ContextItem) => onAttach(item),
    onValueChange: setValue,
    textareaRef,
  });
  return (
    <div>
      <MentionPopover
        open={mention.open}
        items={mention.filtered}
        selectedIndex={mention.selectedIndex}
        onSelect={mention.attachCandidate}
        onHighlight={mention.setSelectedIndex}
      />
      <textarea
        ref={textareaRef}
        data-testid="input"
        value={value}
        onChange={(e) => { setValue(e.target.value); mention.syncFromInput(e.target); }}
        onSelect={(e) => mention.syncFromInput(e.currentTarget)}
        onKeyDown={(e) => {
          if (mention.handleKeyDown(e)) return;
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            onSend(value);
          }
        }}
      />
    </div>
  );
}

function type(text: string, caret = text.length) {
  const el = screen.getByTestId<HTMLTextAreaElement>('input');
  fireEvent.change(el, { target: { value: text, selectionStart: caret, selectionEnd: caret } });
  return el;
}

beforeEach(() => {
  onAttach.mockReset();
  onSend.mockReset();
  useContextCandidatesMock.mockClear();
});

describe('useMentionPicker + MentionPopover', () => {
  it('stays closed on plain text and does not arm candidate fetching', () => {
    render(<Harness />);
    type('hello');
    expect(screen.queryByRole('listbox')).toBeNull();
    expect(useContextCandidatesMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ enabled: false }),
    );
  });

  it('opens on @ and shows all candidate types; arms fetching', () => {
    render(<Harness />);
    type('@');
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    expect(screen.getAllByRole('option')).toHaveLength(5);
    expect(useContextCandidatesMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ enabled: true, glossaryAllBooks: true }),
    );
  });

  it('does NOT open for @ inside a word (email)', () => {
    render(<Harness />);
    type('mail a@b');
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('filters live as the user types, ranking startsWith above contains', () => {
    render(<Harness />);
    type('@Lâm');
    const labels = screen.getAllByRole('option').map((o) => o.textContent);
    expect(labels).toHaveLength(2);
    expect(labels[0]).toContain('Lâm Tuyệt'); // startsWith beats contains
    expect(labels[1]).toContain('Hồ Lâm');
  });

  it('navigates with ArrowDown/ArrowUp (aria-selected follows)', () => {
    render(<Harness />);
    const el = type('@Lâm');
    fireEvent.keyDown(el, { key: 'ArrowDown' });
    let opts = screen.getAllByRole('option');
    expect(opts[1]).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(el, { key: 'ArrowUp' });
    opts = screen.getAllByRole('option');
    expect(opts[0]).toHaveAttribute('aria-selected', 'true');
  });

  it('Enter attaches the highlighted candidate, removes the @query, and does NOT send', () => {
    render(<Harness />);
    const el = type('ask about @Lâm');
    fireEvent.keyDown(el, { key: 'Enter' });
    expect(onAttach).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'e1', type: 'glossary', label: 'Lâm Tuyệt', bookId: 'b1' }),
    );
    expect(onSend).not.toHaveBeenCalled();
    expect(el.value).toBe('ask about '); // @query removed — mention became a chip
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('Tab attaches too', () => {
    render(<Harness />);
    const el = type('@Chapter');
    fireEvent.keyDown(el, { key: 'Tab' });
    expect(onAttach).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'c1', type: 'chapter', chapterId: 'c1' }),
    );
    expect(el.value).toBe('');
  });

  it('mouse click attaches the clicked candidate', () => {
    render(<Harness />);
    const el = type('@Thư');
    fireEvent.click(screen.getAllByRole('option')[0]);
    expect(onAttach).toHaveBeenCalledWith(expect.objectContaining({ id: 'b1', type: 'book' }));
    expect(el.value).toBe('');
  });

  it('Escape closes without attaching and Enter then sends; a new @ reopens', () => {
    render(<Harness />);
    const el = type('@Lâm');
    fireEvent.keyDown(el, { key: 'Escape' });
    expect(screen.queryByRole('listbox')).toBeNull();
    fireEvent.keyDown(el, { key: 'Enter' });
    expect(onSend).toHaveBeenCalledWith('@Lâm');
    expect(onAttach).not.toHaveBeenCalled();
    // typing a fresh @ (different position) reopens
    type('@Lâm @Hồ');
    expect(screen.getByRole('listbox')).toBeInTheDocument();
  });

  it('closes when the query matches nothing (Enter falls through to send)', () => {
    render(<Harness />);
    const el = type('@zzz-no-match');
    expect(screen.queryByRole('listbox')).toBeNull();
    fireEvent.keyDown(el, { key: 'Enter' });
    expect(onSend).toHaveBeenCalled();
  });

  it('closes when the caret moves out of the mention token', () => {
    render(<Harness />);
    const el = type('@Lâm');
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    // move caret to position 0 (before the @) via onSelect
    el.setSelectionRange(0, 0);
    fireEvent.select(el);
    expect(screen.queryByRole('listbox')).toBeNull();
  });
});
