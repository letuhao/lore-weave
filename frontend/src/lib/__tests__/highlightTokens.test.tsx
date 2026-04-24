import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { highlightTokens } from '../highlightTokens';

function renderAsFragment(nodes: ReturnType<typeof highlightTokens>) {
  return render(<div data-testid="out">{nodes}</div>);
}

describe('highlightTokens', () => {
  it('returns the original text unchanged when the query is empty', () => {
    const { getByTestId } = renderAsFragment(highlightTokens('Hello world', ''));
    expect(getByTestId('out').innerHTML).toBe('Hello world');
  });

  it('returns the original text unchanged when every token is <2 chars', () => {
    // Documented CJK limitation: single-char CJK searches lose
    // highlighting. Latin 1-char also filtered to keep behaviour
    // consistent and the regex cheap.
    const { getByTestId } = renderAsFragment(highlightTokens('Hello a b', 'a b'));
    expect(getByTestId('out').innerHTML).toBe('Hello a b');
  });

  it('wraps each matching token in a <mark> element (case-insensitive)', () => {
    const { getByTestId } = renderAsFragment(
      highlightTokens('Hello World, hello WORLD', 'hello'),
    );
    const marks = getByTestId('out').querySelectorAll('mark');
    expect(marks.length).toBe(2);
    // Preserves original case in the render.
    expect(marks[0].textContent).toBe('Hello');
    expect(marks[1].textContent).toBe('hello');
  });

  it('wraps multiple tokens in an OR pattern', () => {
    const { getByTestId } = renderAsFragment(
      highlightTokens('the bridge duel at dawn', 'bridge duel'),
    );
    const marks = getByTestId('out').querySelectorAll('mark');
    expect([...marks].map((m) => m.textContent)).toEqual(['bridge', 'duel']);
  });

  it('escapes regex special characters in tokens (no ReDoS / literal match)', () => {
    // `.+` as a query would match everything without escaping. With
    // escape, only the literal string ".+" is wrapped.
    const { getByTestId } = renderAsFragment(
      highlightTokens('before .+ after', '.+'),
    );
    expect(getByTestId('out').querySelectorAll('mark').length).toBe(1);
    expect(getByTestId('out').querySelector('mark')!.textContent).toBe('.+');
  });

  it('returns original text when no token matches', () => {
    const { getByTestId } = renderAsFragment(
      highlightTokens('hello world', 'xyz'),
    );
    expect(getByTestId('out').querySelector('mark')).toBeNull();
    expect(getByTestId('out').innerHTML).toBe('hello world');
  });

  it('preserves leading/trailing whitespace and adjacency in the output', () => {
    // Regression lock: naive implementations that rebuild the string
    // from tokens split on the pattern can drop spaces around matches.
    const { getByTestId } = renderAsFragment(
      highlightTokens('  hello  ', 'hello'),
    );
    expect(getByTestId('out').textContent).toBe('  hello  ');
  });

  it('matches leftmost-alternative on overlapping-prefix tokens (documented limitation)', () => {
    // /review-impl [LOW#7]: OR-regex ``(he|hell)`` on "hello" matches
    // "he" only — "hell" never wins because regex alternation picks
    // the leftmost alternative that matches at a given position.
    // Future fix would sort tokens by length desc; until then, this
    // test anchors the intentional simplicity so a well-meaning
    // "fix" doesn't go in unnoticed.
    const { getByTestId } = renderAsFragment(
      highlightTokens('hello world', 'he hell'),
    );
    const marks = getByTestId('out').querySelectorAll('mark');
    expect(marks.length).toBe(1);
    expect(marks[0].textContent).toBe('he');
    // Remaining "llo" stays unwrapped.
    expect(getByTestId('out').textContent).toBe('hello world');
  });
});
