// F3 — the AUTHOR's door onto their own marks.
//
// Phase D shipped `create` + `list` wired and nothing else: resolve/dismiss/reopen/remove existed
// on the API and on the co-writer's MCP tool, and on no surface the author could reach. The agent
// could close the author's own annotation and the author could not. These pin that door open —
// the same failure this sweep already found on scene_link and entity_override.
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
import { toast } from 'sonner';

import { ErrorBlockList } from '../ErrorBlockList';
import { actionableBlocks } from '../../hooks/useErrorBlockActions';
import type { ErrorBlock } from '../../errorBlocks';

const block = (over: Partial<ErrorBlock> = {}): ErrorBlock => ({
  id: 'b1', status: 'open', kind: 'continuity', note: 'she was in the tower',
  quote: 'Her vision blurred', start_offset: 0, end_offset: 18,
  source_fingerprint: 'fp', version: 1, ...over,
} as ErrorBlock);

const mkActions = () => ({
  resolve: vi.fn(), dismiss: vi.fn(), reopen: vi.fn(),
  remove: vi.fn(), restore: vi.fn(), busy: false,
});

beforeEach(() => {
  vi.mocked(toast.success).mockReset();
  vi.mocked(toast.error).mockReset();
});

describe('ErrorBlockList (F3 — the author can close their own marks)', () => {
  it('renders the quote and the note so the row is readable without the prose', () => {
    render(<ErrorBlockList blocks={[block()]} driftedIds={[]} actions={mkActions()} />);
    expect(screen.getByTestId('error-block-row').textContent).toContain('Her vision blurred');
    expect(screen.getByTestId('error-block-row').textContent).toContain('she was in the tower');
  });

  it('an unmarked manuscript renders NOTHING — no empty panel stealing editor height', () => {
    const { container } = render(<ErrorBlockList blocks={[]} driftedIds={[]} actions={mkActions()} />);
    expect(container.firstChild).toBeNull();
  });

  it('offers resolve + dismiss on an OPEN mark, and both reach the server', () => {
    const a = mkActions();
    render(<ErrorBlockList blocks={[block()]} driftedIds={[]} actions={a} />);
    fireEvent.click(screen.getByTestId('error-block-resolve-b1'));
    expect(a.resolve).toHaveBeenCalledWith('b1');
    fireEvent.click(screen.getByTestId('error-block-dismiss-b1'));
    expect(a.dismiss).toHaveBeenCalledWith('b1');
  });

  it('a CLOSED mark offers reopen instead — the close is not one-way', () => {
    const a = mkActions();
    render(<ErrorBlockList blocks={[block({ status: 'resolved' })]} driftedIds={[]} actions={a} />);
    expect(screen.queryByTestId('error-block-resolve-b1')).toBeNull();
    fireEvent.click(screen.getByTestId('error-block-reopen-b1'));
    expect(a.reopen).toHaveBeenCalledWith('b1');
  });

  it('removing offers an Undo that RESTORES — the list filters archived rows, so this is the way back', () => {
    const a = mkActions();
    a.remove.mockImplementation((id: string, cb: (i: string) => void) => cb(id));
    render(<ErrorBlockList blocks={[block()]} driftedIds={[]} actions={a} />);
    fireEvent.click(screen.getByTestId('error-block-remove-b1'));

    const [, opts] = vi.mocked(toast.success).mock.calls[0];
    expect(opts?.action).toBeTruthy();
    (opts!.action as { onClick: () => void }).onClick();
    expect(a.restore).toHaveBeenCalledWith('b1', expect.any(Function));
  });

  it('a DRIFTED mark is badged — it can no longer be drawn, so this row is where it lives', () => {
    render(<ErrorBlockList blocks={[block()]} driftedIds={['b1']} actions={mkActions()} />);
    expect(screen.getByTestId('error-block-drifted')).toBeInTheDocument();
  });
});

describe('actionableBlocks', () => {
  it('KEEPS orphaned marks — the document cannot show them, so hiding them here strands them', () => {
    const rows = actionableBlocks([
      block({ id: 'a', status: 'open' }),
      block({ id: 'b', status: 'orphaned' }),
      block({ id: 'c', status: 'proposed' }),
      block({ id: 'd', status: 'resolved' }),
    ]);
    expect(rows.map((r) => r.id)).toEqual(['a', 'b', 'c']);
  });
});
