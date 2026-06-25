import { useState } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LiveStateProvider, useLiveStream } from '../LiveStateContext';

// The hoist owns ONE useCompositionStream. Track MOUNTS (a useEffect, once per
// mount — NOT per render) to prove a consumer remount does NOT remount the stream
// owner (the T5.4 no-remount-across-windows invariant; a remount would reset the
// ghost/AbortController and kill an in-flight generation).
const mounts = vi.hoisted(() => ({ n: 0 }));
vi.mock('../../hooks/useCompositionStream', async () => {
  const React = await vi.importActual<typeof import('react')>('react');
  return {
    useCompositionStream: () => {
      React.useEffect(() => { mounts.n += 1; }, []);
      return { ghost: '', streaming: false, start: vi.fn(), stop: vi.fn(), clearGhost: vi.fn() };
    },
  };
});

beforeEach(() => { mounts.n = 0; });

function Consumer() {
  const s = useLiveStream();
  return <div data-testid="consumer">{String(s.streaming)}</div>;
}

describe('LiveStateContext (T5.4 M1 hoist)', () => {
  it('throws when used outside a provider (no silent un-hoisted stream)', () => {
    // suppress the expected error log
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => renderHook(() => useLiveStream())).toThrow(/LiveStateProvider/);
    spy.mockRestore();
  });

  it('the provider owns exactly ONE stream, and a consumer remount does not create a new one', () => {
    function Harness() {
      const [show, setShow] = useState(true);
      return (
        <LiveStateProvider token="t">
          <button data-testid="toggle" onClick={() => setShow((v) => !v)}>toggle</button>
          {show ? <Consumer /> : null}
        </LiveStateProvider>
      );
    }
    render(<Harness />);
    expect(mounts.n).toBe(1);             // provider mounted → one stream owner
    expect(screen.getByTestId('consumer')).toBeInTheDocument();
    // unmount + remount the CONSUMER (a windowing move re-parents it like this)
    fireEvent.click(screen.getByTestId('toggle')); // consumer unmounts
    fireEvent.click(screen.getByTestId('toggle')); // consumer remounts
    expect(screen.getByTestId('consumer')).toBeInTheDocument();
    expect(mounts.n).toBe(1);             // STILL one — the stream owner never remounted
  });

  it('a changed key REMOUNTS the provider (the book-change stream reset, /review-impl M1)', () => {
    // WorkspaceShell keys the provider by bookId so a book change resets the stream
    // (it used to live inside the key={bookId} CompositionPanel). A key change must
    // remount the owner — proven here so the reset contract can't silently regress.
    const { rerender } = render(<LiveStateProvider key="bookA" token="t"><Consumer /></LiveStateProvider>);
    expect(mounts.n).toBe(1);
    rerender(<LiveStateProvider key="bookB" token="t"><Consumer /></LiveStateProvider>);
    expect(mounts.n).toBe(2);             // new key → provider remounted → fresh stream
  });
});
