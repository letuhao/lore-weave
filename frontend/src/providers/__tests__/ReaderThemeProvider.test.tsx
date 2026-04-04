import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { ReaderThemeProvider, useReaderTheme, READER_PRESETS } from '../ReaderThemeProvider';

function TestConsumer() {
  const { theme, presetName, cssVars, setPreset, setFontSize } = useReaderTheme();
  return (
    <div>
      <span data-testid="preset">{presetName}</span>
      <span data-testid="bg">{theme.bg}</span>
      <span data-testid="font-size">{theme.fontSize}</span>
      <span data-testid="css-var-bg">{cssVars['--reader-bg']}</span>
      <button onClick={() => setPreset('sepia')}>sepia</button>
      <button onClick={() => setFontSize(20)}>bigger</button>
    </div>
  );
}

describe('ReaderThemeProvider', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('defaults to dark preset', () => {
    render(
      <ReaderThemeProvider><TestConsumer /></ReaderThemeProvider>,
    );
    expect(screen.getByTestId('preset').textContent).toBe('dark');
    expect(screen.getByTestId('bg').textContent).toBe('#181412');
  });

  it('loads saved preset from localStorage', () => {
    localStorage.setItem('lw_reader_theme', JSON.stringify({ presetName: 'sepia', overrides: {} }));
    render(
      <ReaderThemeProvider><TestConsumer /></ReaderThemeProvider>,
    );
    expect(screen.getByTestId('preset').textContent).toBe('sepia');
    expect(screen.getByTestId('bg').textContent).toBe('#f4ecd8');
  });

  it('setPreset changes theme and persists', async () => {
    render(
      <ReaderThemeProvider><TestConsumer /></ReaderThemeProvider>,
    );
    await act(async () => {
      screen.getByText('sepia').click();
    });
    expect(screen.getByTestId('preset').textContent).toBe('sepia');
    const saved = JSON.parse(localStorage.getItem('lw_reader_theme')!);
    expect(saved.presetName).toBe('sepia');
  });

  it('setFontSize overrides preset value', async () => {
    render(
      <ReaderThemeProvider><TestConsumer /></ReaderThemeProvider>,
    );
    await act(async () => {
      screen.getByText('bigger').click();
    });
    expect(screen.getByTestId('font-size').textContent).toBe('20');
  });

  it('generates correct cssVars', () => {
    render(
      <ReaderThemeProvider><TestConsumer /></ReaderThemeProvider>,
    );
    expect(screen.getByTestId('css-var-bg').textContent).toBe('#181412');
  });

  it('handles corrupted localStorage gracefully', () => {
    localStorage.setItem('lw_reader_theme', 'bad-json');
    render(
      <ReaderThemeProvider><TestConsumer /></ReaderThemeProvider>,
    );
    expect(screen.getByTestId('preset').textContent).toBe('dark');
  });
});

describe('READER_PRESETS', () => {
  it('has 6 presets', () => {
    expect(Object.keys(READER_PRESETS)).toHaveLength(6);
  });

  it('all presets have required fields', () => {
    for (const preset of Object.values(READER_PRESETS)) {
      expect(preset).toHaveProperty('name');
      expect(preset).toHaveProperty('bg');
      expect(preset).toHaveProperty('fg');
      expect(preset).toHaveProperty('fontFamily');
      expect(preset).toHaveProperty('fontSize');
      expect(preset).toHaveProperty('lineHeight');
      expect(preset).toHaveProperty('maxWidth');
    }
  });
});

describe('useReaderTheme outside provider', () => {
  it('throws when used outside ReaderThemeProvider', () => {
    function Bad() {
      useReaderTheme();
      return null;
    }
    expect(() => render(<Bad />)).toThrow('useReaderTheme outside provider');
  });
});
