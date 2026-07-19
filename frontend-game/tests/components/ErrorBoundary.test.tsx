import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { ErrorBoundary } from '@/components/shared/ErrorBoundary';
import type { JSX } from 'react';

function Boom(): JSX.Element {
  throw new Error('boom');
}

describe('ErrorBoundary', () => {
  it('renders children when they do not throw', () => {
    const { getByText } = render(
      <ErrorBoundary fallback={<span>fallback</span>}>
        <span>ok</span>
      </ErrorBoundary>,
    );
    expect(getByText('ok')).toBeTruthy();
  });

  it('renders the fallback when a child throws (instead of unmounting the tree)', () => {
    // React logs the caught error to console.error — silence it for this case.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { getByText, queryByText } = render(
      <ErrorBoundary fallback={<span>fallback</span>}>
        <Boom />
      </ErrorBoundary>,
    );
    expect(getByText('fallback')).toBeTruthy();
    expect(queryByText('ok')).toBeNull();
    spy.mockRestore();
  });

  it('resets (retries children) when resetKey changes', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { getByText, rerender } = render(
      <ErrorBoundary fallback={<span>fallback</span>} resetKey="a">
        <Boom />
      </ErrorBoundary>,
    );
    expect(getByText('fallback')).toBeTruthy();
    // New resetKey + non-throwing children ⇒ boundary clears and renders them.
    rerender(
      <ErrorBoundary fallback={<span>fallback</span>} resetKey="b">
        <span>recovered</span>
      </ErrorBoundary>,
    );
    expect(getByText('recovered')).toBeTruthy();
    spy.mockRestore();
  });
});
