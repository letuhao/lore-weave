import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { StudioActivityBar } from '../StudioActivityBar';

// Global react-i18next mock returns KEYS, so labels assert on keys.
const setup = (over: Partial<Parameters<typeof StudioActivityBar>[0]> = {}) => {
  const onSelect = vi.fn();
  render(
    <MemoryRouter>
      <StudioActivityBar bookId="b1" activeView="manuscript" sidebarCollapsed={false} onSelect={onSelect} {...over} />
    </MemoryRouter>,
  );
  return { onSelect };
};

describe('StudioActivityBar', () => {
  it('renders all four navigators + a settings link', () => {
    setup();
    ['manuscript', 'bible', 'search', 'quality'].forEach((v) =>
      expect(screen.getByTestId(`studio-activity-${v}`)).toBeTruthy(),
    );
    expect(screen.getByRole('link')).toHaveProperty('href', expect.stringContaining('/books/b1/settings'));
  });

  it('marks the active view pressed (sidebar open)', () => {
    setup({ activeView: 'bible' });
    expect(screen.getByTestId('studio-activity-bible').getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByTestId('studio-activity-manuscript').getAttribute('aria-pressed')).toBe('false');
  });

  it('shows NO active highlight when the sidebar is collapsed', () => {
    setup({ activeView: 'bible', sidebarCollapsed: true });
    expect(screen.getByTestId('studio-activity-bible').getAttribute('aria-pressed')).toBe('false');
  });

  it('fires onSelect with the clicked view', () => {
    const { onSelect } = setup();
    fireEvent.click(screen.getByTestId('studio-activity-search'));
    expect(onSelect).toHaveBeenCalledWith('search');
  });
});
