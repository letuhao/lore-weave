// Sheet — the addressable bottom-sheet primitive (spec MB4). Which sheet is open lives in
// the URL (?sheet=<id>), so a deep-link restores it and hardware Back closes it. These tests
// pin: open iff the param matches; open pushes / close replaces; a non-matching param stays
// closed; a cold deep-link opens the sheet immediately.
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
}));

import { Sheet, useSheetRoute } from '../Sheet';

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="loc">{loc.search}</div>;
}

function Harness() {
  const { openSheet } = useSheetRoute();
  return (
    <>
      <button data-testid="open" onClick={() => openSheet('today')}>
        open
      </button>
      <Sheet id="today" title="Today so far">
        <div data-testid="sheet-body">the day&apos;s captures</div>
      </Sheet>
      <LocationProbe />
    </>
  );
}

function renderAt(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Harness />
    </MemoryRouter>,
  );
}

describe('Sheet — addressability', () => {
  it('is closed when no ?sheet param is present', () => {
    renderAt('/x');
    expect(screen.queryByTestId('sheet-today')).toBeNull();
  });

  it('a cold deep-link ?sheet=today opens the sheet immediately', () => {
    renderAt('/x?sheet=today');
    expect(screen.getByTestId('sheet-today')).toBeTruthy();
    expect(screen.getByTestId('sheet-body')).toBeTruthy();
  });

  it('a non-matching ?sheet value does NOT open this sheet', () => {
    renderAt('/x?sheet=other');
    expect(screen.queryByTestId('sheet-today')).toBeNull();
  });

  it('openSheet sets ?sheet=today and renders the sheet', () => {
    renderAt('/x');
    fireEvent.click(screen.getByTestId('open'));
    expect(screen.getByTestId('loc').textContent).toContain('sheet=today');
    expect(screen.getByTestId('sheet-today')).toBeTruthy();
  });

  it('the Close button strips the param and hides the sheet', () => {
    renderAt('/x?sheet=today');
    expect(screen.getByTestId('sheet-today')).toBeTruthy();
    // The mocked t() echoes the key, so the Close control's aria-label is the i18n key.
    fireEvent.click(screen.getByLabelText('common.close'));
    expect(screen.queryByTestId('sheet-today')).toBeNull();
    expect(screen.getByTestId('loc').textContent).not.toContain('sheet=today');
  });
});
