import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ThemeCustomizer } from '../ThemeCustomizer';

vi.mock('@/providers/ThemeProvider', () => ({
  useReaderTheme: () => ({
    theme: { fontFamily: "'Lora', serif", fontSize: 18, lineHeight: 1.6, maxWidth: 680, spacing: 1.2 },
    presetName: 'dark',
    presets: { dark: { bg: '#000', fg: '#fff', name: 'Dark' } },
    setPreset: vi.fn(), setFont: vi.fn(), setFontSize: vi.fn(),
    setLineHeight: vi.fn(), setMaxWidth: vi.fn(), setSpacing: vi.fn(),
  }),
}));

const baseProps = {
  open: true,
  onClose: vi.fn(),
  showIndices: false,
  onShowIndicesChange: vi.fn(),
  autoNext: true,
  onAutoNextChange: vi.fn(),
  autoScrollTTS: true,
  onAutoScrollTTSChange: vi.fn(),
};

const checkboxFor = (label: string) =>
  screen.getByText(label).closest('label')!.querySelector('input') as HTMLInputElement;

describe('ThemeCustomizer reading-mode toggles (UI-3a/b drift fix)', () => {
  it('Auto-load next chapter is enabled (not "coming soon"), reflects state, and toggles', () => {
    const onAutoNextChange = vi.fn();
    render(<ThemeCustomizer {...baseProps} autoNext={true} onAutoNextChange={onAutoNextChange} />);
    const cb = checkboxFor('Auto-load next chapter');
    expect(cb.disabled).toBe(false);
    expect(cb.checked).toBe(true);
    fireEvent.click(cb);
    expect(onAutoNextChange).toHaveBeenCalledWith(false);
    // No stale "coming soon" copy remains.
    expect(screen.queryByText(/coming soon/i)).toBeNull();
  });

  it('Auto-scroll with TTS is enabled, reflects state, and toggles', () => {
    const onAutoScrollTTSChange = vi.fn();
    render(<ThemeCustomizer {...baseProps} autoScrollTTS={false} onAutoScrollTTSChange={onAutoScrollTTSChange} />);
    const cb = checkboxFor('Auto-scroll with TTS');
    expect(cb.disabled).toBe(false);
    expect(cb.checked).toBe(false);
    fireEvent.click(cb);
    expect(onAutoScrollTTSChange).toHaveBeenCalledWith(true);
  });
});
