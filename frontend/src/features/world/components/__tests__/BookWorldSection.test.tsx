import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

// Stub WorldPicker to a pair of controls: "pick" emits a world id, "clear"
// emits null — so we can drive both link and unlink paths.
vi.mock('@/components/shared/WorldPicker', () => ({
  WorldPicker: ({ value, onChange }: { value: string | null; onChange: (id: string | null) => void }) => (
    <div data-testid="stub-world-picker" data-value={value ?? ''}>
      <button type="button" data-testid="stub-pick" onClick={() => onChange('w-new')}>pick</button>
      <button type="button" data-testid="stub-clear" onClick={() => onChange(null)}>clear</button>
    </div>
  ),
}));

const link = vi.fn();
const unlink = vi.fn();
const hook = vi.fn();
vi.mock('../../hooks/useBookWorldLink', () => ({
  useBookWorldLink: () => hook(),
}));

import { BookWorldSection } from '../BookWorldSection';

function renderSection(worldId: string | null, onChanged = vi.fn(), onOpenWorld = vi.fn()) {
  render(
    <BookWorldSection bookId="b1" worldId={worldId} onChanged={onChanged} onOpenWorld={onOpenWorld} />,
  );
  return { onChanged, onOpenWorld };
}

beforeEach(() => {
  link.mockReset();
  unlink.mockReset();
  hook.mockReturnValue({ link, unlink, isPending: false, error: null });
});

describe('BookWorldSection (W6/G3)', () => {
  it('shows NO "open in world" backlink when the book is standalone', () => {
    renderSection(null);
    expect(screen.queryByTestId('book-open-in-world')).toBeNull();
  });

  it('attaches the book when a world is picked, then reloads', async () => {
    link.mockResolvedValue({ book_id: 'b1', world_id: 'w-new' });
    const { onChanged } = renderSection(null);
    fireEvent.click(screen.getByTestId('stub-pick'));
    await waitFor(() => expect(link).toHaveBeenCalledWith('w-new'));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it('invokes the injected onOpenWorld (DOCK-7 — caller decides navigate vs. studio-link) when "open in world" is clicked', () => {
    const { onOpenWorld } = renderSection('w-cur');
    fireEvent.click(screen.getByTestId('book-open-in-world'));
    expect(onOpenWorld).toHaveBeenCalledWith('w-cur');
  });

  it('detaches the book when the world is cleared', async () => {
    unlink.mockResolvedValue(undefined);
    const { onChanged } = renderSection('w-cur');
    fireEvent.click(screen.getByTestId('stub-clear'));
    await waitFor(() => expect(unlink).toHaveBeenCalledWith('w-cur'));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });
});
