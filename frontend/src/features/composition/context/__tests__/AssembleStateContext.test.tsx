import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { AssembleStateProvider, useAssembleStateOptional } from '../AssembleStateContext';
import type { ChapterGeneration } from '../../types';

// WS-D cross-window Assemble-draft sync. jsdom/Node provide BroadcastChannel; two
// providers on the same (book, chapter) talk. NOTE: ids are file-unique (ASMB_*) —
// Node shares BroadcastChannel across vitest worker threads, so a generic 'b1' would
// cross-talk with the other popout-channel test files and flake (see popoutChannel.test).

const DRAFT = { job_id: 'j1', status: 'completed', text: 'DRAFT' } as unknown as ChapterGeneration;

function Consumer({ label }: { label: string }) {
  const s = useAssembleStateOptional();
  if (!s) return <span data-testid={`${label}-none`}>no-provider</span>;
  return (
    <div>
      <span data-testid={`${label}-result`}>{s.result?.text ?? 'none'}</span>
      <span data-testid={`${label}-edited`}>{s.edited || 'empty'}</span>
      <button data-testid={`${label}-set`} onClick={() => { s.setResult(DRAFT); s.setEdited('edited prose'); }}>set</button>
      <button data-testid={`${label}-clear`} onClick={() => { s.setResult(null); s.setEdited(''); }}>clear</button>
    </div>
  );
}

afterEach(() => { /* RTL auto-cleanup unmounts providers → channels close */ });

describe('AssembleStateContext (WS-D — cross-window Assemble draft)', () => {
  it('useAssembleStateOptional returns null with no provider (bare mount fallback)', () => {
    render(<Consumer label="bare" />);
    expect(screen.getByTestId('bare-none')).toBeTruthy();
  });

  it('broadcasts a local change to a peer window on the SAME (book,chapter)', async () => {
    render(
      <>
        <AssembleStateProvider bookId="ASMB_bcast" chapterId="c1"><Consumer label="opener" /></AssembleStateProvider>
        <AssembleStateProvider bookId="ASMB_bcast" chapterId="c1"><Consumer label="popout" /></AssembleStateProvider>
      </>,
    );
    fireEvent.click(screen.getByTestId('opener-set'));
    // the peer receives the draft over the channel (no broadcast loop — echo-guarded)
    await waitFor(() => expect(screen.getByTestId('popout-result')).toHaveTextContent('DRAFT'));
    expect(screen.getByTestId('popout-edited')).toHaveTextContent('edited prose');
  });

  it('a freshly-mounted window hydrates the current draft via request→reply', async () => {
    render(<AssembleStateProvider bookId="ASMB_req" chapterId="c1"><Consumer label="opener" /></AssembleStateProvider>);
    fireEvent.click(screen.getByTestId('opener-set'));
    // a second window mounts AFTER the draft exists → it asks, the opener replies
    render(<AssembleStateProvider bookId="ASMB_req" chapterId="c1"><Consumer label="popout" /></AssembleStateProvider>);
    await waitFor(() => expect(screen.getByTestId('popout-result')).toHaveTextContent('DRAFT'));
  });

  it('flushes the pending draft to peers on unmount (no lost last-edit on a pop-out close)', async () => {
    render(<AssembleStateProvider bookId="ASMB_flush" chapterId="c1"><Consumer label="opener" /></AssembleStateProvider>);
    const pop = render(<AssembleStateProvider bookId="ASMB_flush" chapterId="c1"><Consumer label="popout" /></AssembleStateProvider>);
    // set on the popout (arms the 250ms debounce), then close it immediately
    fireEvent.click(screen.getByTestId('popout-set'));
    pop.unmount();   // cleanup flushes the pending broadcast BEFORE closing the channel
    await waitFor(() => expect(screen.getByTestId('opener-result')).toHaveTextContent('DRAFT'));
  });

  it('does NOT cross different chapters of the same book', async () => {
    render(
      <>
        <AssembleStateProvider bookId="ASMB_chap" chapterId="c1"><Consumer label="ch1" /></AssembleStateProvider>
        <AssembleStateProvider bookId="ASMB_chap" chapterId="c2"><Consumer label="ch2" /></AssembleStateProvider>
      </>,
    );
    fireEvent.click(screen.getByTestId('ch1-set'));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByTestId('ch2-result')).toHaveTextContent('none'); // c2 never sees c1's draft
  });
});
