import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MatchSnippet } from '../MatchSnippet';

// i18n returns the key in tests; match_field.* falls back to defaultValue (the
// raw field_code), so we assert on the snippet text + the <mark> span.

describe('MatchSnippet', () => {
  it('marks the highlighted rune range (CJK code-point offsets)', () => {
    // "黛玉" at rune offsets [1,3] within "林黛玉".
    render(<MatchSnippet match={{ field_code: 'name', snippet: '林黛玉', highlights: [[1, 3]] }} />);
    const mark = screen.getByText('黛玉');
    expect(mark.tagName).toBe('MARK');
    // The leading unmatched rune is rendered too.
    expect(screen.getByTestId('glossary-match-snippet').textContent).toContain('林黛玉');
  });

  it('renders no <mark> for a trigram-only hit (empty highlights)', () => {
    const { container } = render(
      <MatchSnippet match={{ field_code: 'name', snippet: 'Arthur', highlights: [] }} />,
    );
    expect(container.querySelector('mark')).toBeNull();
    expect(screen.getByTestId('glossary-match-snippet').textContent).toContain('Arthur');
  });

  it('handles multiple non-overlapping highlights in order', () => {
    render(<MatchSnippet match={{ field_code: 'alias', snippet: 'ab cd ef', highlights: [[0, 2], [6, 8]] }} />);
    const marks = screen.getAllByText(/ab|ef/);
    const marked = marks.filter((m) => m.tagName === 'MARK').map((m) => m.textContent);
    expect(marked).toEqual(['ab', 'ef']);
  });
});
