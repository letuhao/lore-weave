import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { LayoutPicker } from '../LayoutPicker';
import { LAYOUT_PRESETS, MIN_COLUMN_PX } from '../dockLayout';

describe('LayoutPicker', () => {
  it('renders every preset with a glyph', () => {
    render(<LayoutPicker panelCount={4} dockWidth={4000} onPick={vi.fn()} />);
    for (const p of LAYOUT_PRESETS) {
      expect(screen.getByTestId(`studio-layout-preset-${p.id}`)).toBeTruthy();
    }
  });

  it('picking an enabled preset reports it', () => {
    const onPick = vi.fn();
    render(<LayoutPicker panelCount={4} dockWidth={4000} onPick={onPick} />);
    fireEvent.click(screen.getByTestId('studio-layout-preset-cols4'));
    expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ id: 'cols4', cols: 4, rows: 1 }));
  });

  it('with <2 panels every multi-cell preset is disabled but Single stays enabled', () => {
    render(<LayoutPicker panelCount={1} dockWidth={4000} onPick={vi.fn()} />);
    expect((screen.getByTestId('studio-layout-preset-single') as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByTestId('studio-layout-preset-cols2') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId('studio-layout-preset-grid2x2') as HTMLButtonElement).disabled).toBe(true);
  });

  it('flags a preset whose columns would be too narrow on the current dock', () => {
    // 8 columns needs 8×MIN px; a 1400px dock is too narrow for 8 but fine for 2.
    render(<LayoutPicker panelCount={4} dockWidth={MIN_COLUMN_PX * 4} onPick={vi.fn()} />);
    expect((screen.getByTestId('studio-layout-preset-cols8') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId('studio-layout-preset-cols2') as HTMLButtonElement).disabled).toBe(false);
  });

  it('a disabled preset does not report a pick', () => {
    const onPick = vi.fn();
    render(<LayoutPicker panelCount={1} dockWidth={4000} onPick={onPick} />);
    fireEvent.click(screen.getByTestId('studio-layout-preset-cols4'));
    expect(onPick).not.toHaveBeenCalled();
  });

  it('shows the open-panels hint / empty guidance', () => {
    const { rerender } = render(<LayoutPicker panelCount={3} dockWidth={4000} onPick={vi.fn()} />);
    expect(screen.getByTestId('studio-layout-hint').textContent).toContain('layout.hint');
    rerender(<LayoutPicker panelCount={0} dockWidth={4000} onPick={vi.fn()} />);
    expect(screen.getByTestId('studio-layout-hint').textContent).toContain('layout.empty');
  });
});
