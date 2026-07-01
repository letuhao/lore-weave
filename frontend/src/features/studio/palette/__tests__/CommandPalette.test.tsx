import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import { StudioHostProvider } from '../../host/StudioHostProvider';
import { CommandPalette } from '../CommandPalette';

const wrap = (ui: ReactNode) => render(<StudioHostProvider bookId="b1">{ui}</StudioHostProvider>);
const chrome = () => ({ setActiveView: vi.fn(), toggleSidebar: vi.fn(), toggleBottom: vi.fn() });

describe('CommandPalette', () => {
  it('renders chrome commands (no registered panels yet)', () => {
    wrap(<CommandPalette open onClose={vi.fn()} chrome={chrome()} onOpenQuickOpen={vi.fn()} onOpenPanel={vi.fn()} />);
    expect(screen.getByTestId('palette-entry-view.toggleBottom')).toBeTruthy();
    expect(screen.getByTestId('palette-entry-view.showManuscript')).toBeTruthy();
    // no Panels group commands (registry empty)
    expect(screen.queryByTestId('palette-entry-studio.openPanel.cast')).toBeNull();
  });

  it('filters commands by the typed query', () => {
    wrap(<CommandPalette open onClose={vi.fn()} chrome={chrome()} onOpenQuickOpen={vi.fn()} onOpenPanel={vi.fn()} />);
    fireEvent.change(screen.getByTestId('palette-input'), { target: { value: 'bottom' } });
    expect(screen.getByTestId('palette-entry-view.toggleBottom')).toBeTruthy();
    expect(screen.queryByTestId('palette-entry-view.showManuscript')).toBeNull();
  });

  it('selecting a command runs it and closes the palette', () => {
    const c = chrome();
    const onClose = vi.fn();
    wrap(<CommandPalette open onClose={onClose} chrome={c} onOpenQuickOpen={vi.fn()} onOpenPanel={vi.fn()} />);
    fireEvent.click(screen.getByTestId('palette-entry-view.showQuality'));
    expect(c.setActiveView).toHaveBeenCalledWith('quality');
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('"Go to Chapter…" opens Quick Open', () => {
    const onOpenQuickOpen = vi.fn();
    wrap(<CommandPalette open onClose={vi.fn()} chrome={chrome()} onOpenQuickOpen={onOpenQuickOpen} onOpenPanel={vi.fn()} />);
    fireEvent.click(screen.getByTestId('palette-entry-view.goToChapter'));
    expect(onOpenQuickOpen).toHaveBeenCalledOnce();
  });
});
