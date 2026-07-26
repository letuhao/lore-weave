// #12 M-H — word count: space-separated words + CJK ideographs/kana counted per char.
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));

const unitState = vi.hoisted(() => ({
  value: null as { state: { chapterId: string | null; textContent: string } } | null,
}));
vi.mock('../../manuscript/unit/ManuscriptUnitProvider', () => ({
  useManuscriptUnit: () => unitState.value,
}));

import { WordCountStatusItem, countWords } from '../WordCountStatusItem';

describe('countWords', () => {
  it('counts space-separated (Vietnamese) words', () => {
    expect(countWords('Lâm Uyển đào thoát qua rừng trúc')).toBe(7);
  });
  it('counts CJK ideographs/kana per character', () => {
    expect(countWords('魔女逆天')).toBe(4);
    expect(countWords('mixed 漢字 words')).toBe(4); // 2 words + 2 ideographs
  });
  it('empty → 0', () => {
    expect(countWords('')).toBe(0);
  });
});

describe('WordCountStatusItem', () => {
  it('renders the live count for the open chapter', () => {
    unitState.value = { state: { chapterId: 'ch1', textContent: 'một hai ba' } };
    render(<WordCountStatusItem />);
    expect(screen.getByTestId('status-word-count').textContent).toContain('3');
  });
  it('placeholder when no chapter is open (or outside the provider)', () => {
    unitState.value = null;
    render(<WordCountStatusItem />);
    expect(screen.getByTestId('status-word-count').textContent).toContain('—');
  });
});
