import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { renderHighlight } from '../renderHighlight';

describe('renderHighlight', () => {
  it('wraps the BE span in <mark> (BMP CJK) without altering surrounding text', () => {
    const { container } = render(<>{renderHighlight('话说乾坤圈是法宝', [[2, 5]])}</>);
    expect(container.querySelector('mark')?.textContent).toBe('乾坤圈');
    expect(container.textContent).toBe('话说乾坤圈是法宝');
  });

  it('indexes by code point, not UTF-16 (supplementary plane — review-impl MED-2)', () => {
    // '𠮷' is ONE code point but TWO UTF-16 units; offset [1,2] must select 'a'.
    // A naive String.slice(1,2) would return half a surrogate pair.
    const { container } = render(<>{renderHighlight('𠮷ab', [[1, 2]])}</>);
    expect(container.querySelector('mark')?.textContent).toBe('a');
  });

  it('renders plain text (no <mark>) when there are no ranges', () => {
    const { container } = render(<>{renderHighlight('hello', [])}</>);
    expect(container.querySelector('mark')).toBeNull();
    expect(container.textContent).toBe('hello');
  });
});
