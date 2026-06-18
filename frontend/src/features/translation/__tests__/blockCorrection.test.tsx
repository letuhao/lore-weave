import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, render, screen, fireEvent } from '@testing-library/react';
import type { ChapterTranslation } from '../api';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const patchBlock = vi.fn();
vi.mock('../api', () => ({ versionsApi: { patchBlock: (...a: unknown[]) => patchBlock(...a) } }));

// Keep the reader renderers light in jsdom (source pane uses them).
vi.mock('@/components/reader/InlineRenderer', () => ({ InlineRenderer: () => <span>inline</span> }));
vi.mock('@/components/reader/ContentRenderer', () => ({ ContentRenderer: () => <div>compound</div> }));

import { useBlockCorrection } from '../hooks/useBlockCorrection';
import { BlockAlignedReview } from '../components/BlockAlignedReview';

const blk = (text: string) => ({ type: 'paragraph', content: [{ type: 'text', text }] });
const VERSION = { id: 'v1', target_language: 'vi', translated_body_format: 'json' } as unknown as ChapterTranslation;

describe('useBlockCorrection', () => {
  beforeEach(() => { patchBlock.mockReset(); patchBlock.mockResolvedValue({}); });

  it('saveBlock patches the right block (rebuilt content + base + source text) and mirrors locally', async () => {
    const onPatched = vi.fn();
    const orig = [blk('原文0'), blk('原文1')];
    const { result } = renderHook(() => useBlockCorrection('ch1', VERSION, orig, onPatched));
    await act(async () => { await result.current.saveBlock(1, 'Sửa rồi', blk('cũ')); });
    expect(patchBlock).toHaveBeenCalledTimes(1);
    const arg = patchBlock.mock.calls[0][2] as Record<string, any>;
    expect(arg.block_index).toBe(1);
    expect(arg.base_version_id).toBe('v1');
    expect(arg.target_language).toBe('vi');
    expect(arg.block.content[0].text).toBe('Sửa rồi');
    expect(arg.source_block_text).toBe('原文1'); // anchored to the source paragraph
    expect(onPatched).toHaveBeenCalledWith(1, expect.objectContaining({ type: 'paragraph' }));
    expect(result.current.dirty.has(1)).toBe(true);
  });

  it('saveBlock skips a no-op edit (no round-trip)', async () => {
    const { result } = renderHook(() => useBlockCorrection('ch1', VERSION, [], vi.fn()));
    await act(async () => { await result.current.saveBlock(0, 'same', blk('same')); });
    expect(patchBlock).not.toHaveBeenCalled();
  });
});

describe('BlockAlignedReview editable mode', () => {
  it('renders an editable cell per translate block and fires onBlockEdit on blur (changed)', () => {
    const onEdit = vi.fn();
    render(
      <BlockAlignedReview
        originalBlocks={[blk('src')]}
        translatedBlocks={[blk('dst')]}
        editable
        onBlockEdit={onEdit}
      />,
    );
    const cell = screen.getByTestId('correction-cell-0');
    fireEvent.change(cell, { target: { value: 'new translation' } });
    fireEvent.blur(cell);
    expect(onEdit).toHaveBeenCalledWith(0, 'new translation', expect.objectContaining({ type: 'paragraph' }));
  });

  it('does not fire onBlockEdit when the text is unchanged', () => {
    const onEdit = vi.fn();
    render(
      <BlockAlignedReview
        originalBlocks={[blk('src')]}
        translatedBlocks={[blk('dst')]}
        editable
        onBlockEdit={onEdit}
      />,
    );
    fireEvent.blur(screen.getByTestId('correction-cell-0'));
    expect(onEdit).not.toHaveBeenCalled();
  });

  it('is read-only (no editable cell) when editable is false', () => {
    render(<BlockAlignedReview originalBlocks={[blk('src')]} translatedBlocks={[blk('dst')]} />);
    expect(screen.queryByTestId('correction-cell-0')).toBeNull();
  });
});
