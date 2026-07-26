import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MobileEditorShell } from '../MobileEditorShell';

const panes = {
  header: <div data-testid="hdr">header</div>,
  editor: <div data-testid="ed">EDITOR</div>,
  studio: <div data-testid="st">STUDIO</div>,
  history: <div data-testid="hi">HISTORY</div>,
};

describe('MobileEditorShell (M5a)', () => {
  it('renders the header + bottom group bar with three groups', () => {
    render(<MobileEditorShell group="editor" onGroupChange={vi.fn()} {...panes} />);
    expect(screen.getByTestId('hdr')).toBeTruthy();
    expect(screen.getByTestId('mobile-tab-editor')).toBeTruthy();
    expect(screen.getByTestId('mobile-tab-studio')).toBeTruthy();
    expect(screen.getByTestId('mobile-tab-history')).toBeTruthy();
  });

  it('all three panes stay MOUNTED (state-preserving); only the active is visible', () => {
    render(<MobileEditorShell group="studio" onGroupChange={vi.fn()} {...panes} />);
    // mounted regardless of active group
    expect(screen.getByTestId('ed')).toBeTruthy();
    expect(screen.getByTestId('st')).toBeTruthy();
    expect(screen.getByTestId('hi')).toBeTruthy();
    // the active group's wrapper is shown; the others carry the `hidden` class
    expect(screen.getByTestId('ed').parentElement?.className).toContain('hidden');
    expect(screen.getByTestId('st').parentElement?.className).not.toContain('hidden');
    expect(screen.getByTestId('hi').parentElement?.className).toContain('hidden');
  });

  it('the active group tab is aria-selected; tapping another switches group', () => {
    const onGroupChange = vi.fn();
    render(<MobileEditorShell group="editor" onGroupChange={onGroupChange} {...panes} />);
    expect(screen.getByTestId('mobile-tab-editor').getAttribute('aria-selected')).toBe('true');
    fireEvent.click(screen.getByTestId('mobile-tab-history'));
    expect(onGroupChange).toHaveBeenCalledWith('history');
  });

  it('exposes the active group via data-testid for the smoke', () => {
    render(<MobileEditorShell group="history" onGroupChange={vi.fn()} {...panes} />);
    const region = screen.getByTestId('mobile-group-history');
    expect(within(region).getByTestId('hi')).toBeTruthy();
  });
});
