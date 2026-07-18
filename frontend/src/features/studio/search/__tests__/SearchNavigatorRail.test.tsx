import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? _k, i18n: { language: 'en' } }),
}));

const host = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock('../../host/StudioHostProvider', () => ({ useStudioHost: () => host.value }));

import { SearchNavigatorRail } from '../SearchNavigatorRail';

describe('SearchNavigatorRail (S-11)', () => {
  beforeEach(() => {
    host.value = { openPanel: vi.fn() };
  });

  it('is a real query rail, not a "Built next" stub', () => {
    render(<SearchNavigatorRail />);
    expect(screen.getByTestId('studio-search-rail')).toBeInTheDocument();
    expect(screen.getByTestId('studio-search-rail-input')).toBeInTheDocument();
  });

  it('submitting seeds the search panel with the typed query + selected mode', () => {
    render(<SearchNavigatorRail />);
    fireEvent.change(screen.getByTestId('studio-search-rail-input'), { target: { value: '  the tower  ' } });
    fireEvent.click(screen.getByTestId('studio-search-rail-mode-semantic'));
    fireEvent.click(screen.getByTestId('studio-search-rail-go'));
    expect(host.value.openPanel).toHaveBeenCalledWith('search', {
      focus: true,
      params: { query: 'the tower', mode: 'semantic' },
    });
  });

  it('defaults to text mode and opens even on an empty query (panel takes over)', () => {
    render(<SearchNavigatorRail />);
    fireEvent.submit(screen.getByTestId('studio-search-rail-input').closest('form')!);
    expect(host.value.openPanel).toHaveBeenCalledWith('search', {
      focus: true,
      params: { query: '', mode: 'text' },
    });
  });
});
