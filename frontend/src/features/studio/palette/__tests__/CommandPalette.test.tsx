import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CommandPalette } from '../CommandPalette';
import type { StudioPanelDef } from '../../panels/catalog';

const chrome = () => ({ setActiveView: vi.fn(), toggleSidebar: vi.fn(), toggleBottom: vi.fn() });
const panel = (id: string): StudioPanelDef =>
  ({ id, component: (() => null) as unknown as StudioPanelDef['component'], titleKey: `panels.${id}.title`, descKey: `panels.${id}.desc` });

const setup = (over: Partial<React.ComponentProps<typeof CommandPalette>> = {}) => {
  const props: React.ComponentProps<typeof CommandPalette> = {
    open: true, onClose: vi.fn(), chrome: chrome(), panels: [], onOpenQuickOpen: vi.fn(), onOpenPanel: vi.fn(), ...over,
  };
  render(<CommandPalette {...props} />);
  return props;
};

describe('CommandPalette', () => {
  it('renders chrome commands; no Panels group when the catalog is empty', () => {
    setup();
    expect(screen.getByTestId('palette-entry-view.toggleBottom')).toBeTruthy();
    expect(screen.getByTestId('palette-entry-view.showManuscript')).toBeTruthy();
    expect(screen.queryByTestId('palette-entry-studio.openPanel.compose')).toBeNull();
  });

  it('lists a "Studio: Open …" command per catalog panel; selecting opens it', () => {
    const onOpenPanel = vi.fn();
    const onClose = vi.fn();
    setup({ panels: [panel('compose')], onOpenPanel, onClose });
    fireEvent.click(screen.getByTestId('palette-entry-studio.openPanel.compose'));
    expect(onOpenPanel).toHaveBeenCalledWith('compose');
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('filters commands by the typed query', () => {
    setup();
    fireEvent.change(screen.getByTestId('palette-input'), { target: { value: 'bottom' } });
    expect(screen.getByTestId('palette-entry-view.toggleBottom')).toBeTruthy();
    expect(screen.queryByTestId('palette-entry-view.showManuscript')).toBeNull();
  });

  it('selecting a command runs it and closes the palette', () => {
    const c = chrome();
    const onClose = vi.fn();
    setup({ chrome: c, onClose });
    fireEvent.click(screen.getByTestId('palette-entry-view.showQuality'));
    expect(c.setActiveView).toHaveBeenCalledWith('quality');
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('"Go to Chapter…" opens Quick Open', () => {
    const onOpenQuickOpen = vi.fn();
    setup({ onOpenQuickOpen });
    fireEvent.click(screen.getByTestId('palette-entry-view.goToChapter'));
    expect(onOpenQuickOpen).toHaveBeenCalledOnce();
  });

  it('renders a command description as the muted sublabel (i18n key from the mock)', () => {
    setup();
    expect(screen.getByTestId('palette-entry-view.toggleBottom').textContent).toContain('palette.desc.toggleBottom');
  });

  it('a run command surfaces in a Recent group on the (empty-query) list', () => {
    setup();
    expect(screen.queryByTestId('palette-entry-recent:view.toggleBottom')).toBeNull();
    fireEvent.click(screen.getByTestId('palette-entry-view.toggleBottom'));
    expect(screen.getByTestId('palette-entry-recent:view.toggleBottom')).toBeTruthy();
  });
});
