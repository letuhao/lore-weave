import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { PopoutHost } from '../PopoutHost';
import { openPopoutChannel, type PopoutMessage } from '../../../workspace/popoutChannel';

// Mock the heavy panel + the auth + the live-stream provider so the test exercises the
// popout SHELL (param parsing, accept-relay, dock-back), not the studio internals.
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../context/LiveStateContext', () => ({
  LiveStateProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('../../CompositionPanel', () => ({
  CompositionPanel: ({ soloPanel, onAccept }: { soloPanel: string; onAccept: (t: string, m?: { model?: string }) => void }) => (
    <div data-testid="solo-panel">
      <span data-testid="solo-id">{soloPanel}</span>
      <button data-testid="emit-accept" onClick={() => onAccept('drafted', { model: 'qwen' })}>accept</button>
    </div>
  ),
}));

function renderAt(query: string) {
  return render(
    <MemoryRouter initialEntries={[`/composition/popout${query}`]}>
      <PopoutHost />
    </MemoryRouter>,
  );
}

describe('PopoutHost (T5.4 M4)', () => {
  it('renders the solo panel for valid params', () => {
    renderAt('?book=b1&chapter=c1&scene=s1&panel=cast');
    expect(screen.getByTestId('solo-panel')).toBeInTheDocument();
    expect(screen.getByTestId('solo-id')).toHaveTextContent('cast');
  });

  it('rejects an unknown panel id (no arbitrary param → render)', () => {
    renderAt('?book=b1&chapter=c1&panel=__nope__');
    expect(screen.queryByTestId('solo-panel')).toBeNull();
    expect(screen.getByText('popout.invalid')).toBeInTheDocument();   // i18n mock returns the key
  });

  it('rejects when required params are missing', () => {
    renderAt('?panel=cast');   // no book/chapter
    expect(screen.queryByTestId('solo-panel')).toBeNull();
  });

  it('relays accepted prose to the opener over the per-book channel', async () => {
    const opener = openPopoutChannel('b1', 'c1');
    const got: PopoutMessage[] = [];
    opener.subscribe((m) => got.push(m));
    renderAt('?book=b1&chapter=c1&panel=compose');
    fireEvent.click(screen.getByTestId('emit-accept'));
    await new Promise((r) => setTimeout(r, 0));
    expect(got).toContainEqual({ kind: 'insert-prose', text: 'drafted', model: 'qwen' });
    opener.close();
  });

  it('dock-back posts dock-back + closes the window', async () => {
    const close = vi.spyOn(window, 'close').mockImplementation(() => {});
    const opener = openPopoutChannel('b9', 'c1');
    const got: PopoutMessage[] = [];
    opener.subscribe((m) => got.push(m));
    renderAt('?book=b9&chapter=c1&panel=grounding');
    fireEvent.click(screen.getByTestId('popout-dock-back'));
    await new Promise((r) => setTimeout(r, 0));
    expect(got).toContainEqual({ kind: 'dock-back', panel: 'grounding' });
    expect(close).toHaveBeenCalledTimes(1);
    opener.close();
    close.mockRestore();
  });
});
