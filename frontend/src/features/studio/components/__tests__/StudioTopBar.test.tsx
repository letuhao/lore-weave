import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { StudioTopBar } from '../StudioTopBar';
import { StudioHostProvider } from '../../host/StudioHostProvider';

// StudioTopBar now hosts the layout-preset button (uses useStudioHost), so the provider is required.
const setup = (bookTitle = 'My Book', onOpenQuickOpen = vi.fn()) =>
  render(
    <MemoryRouter>
      <StudioHostProvider bookId="b1">
        <StudioTopBar bookId="b1" bookTitle={bookTitle} onOpenQuickOpen={onOpenQuickOpen} />
      </StudioHostProvider>
    </MemoryRouter>,
  );

describe('StudioTopBar', () => {
  it('shows the studio title + book title', () => {
    setup('Ma Nữ Nghịch Thiên');
    expect(screen.getByText('title')).toBeTruthy(); // studio title key
    expect(screen.getByText('Ma Nữ Nghịch Thiên')).toBeTruthy();
  });

  it('links back to the books list (not the legacy per-book workspace) and to settings', () => {
    // D-STUDIO-BACK-TO-BOOKS: the back button used to target /books/:bookId (the
    // legacy tabbed workspace) — it now goes to the /books list itself.
    setup();
    const hrefs = screen.getAllByRole('link').map((a) => a.getAttribute('href'));
    expect(hrefs).toContain('/books');
    expect(hrefs).not.toContain('/books/b1');
    expect(hrefs).toContain('/books/b1/settings');
  });

  it('the Quick Open affordance is live and opens Quick Open on click', () => {
    const onOpenQuickOpen = vi.fn();
    setup('My Book', onOpenQuickOpen);
    const palette = screen.getByTestId('studio-command-palette') as HTMLButtonElement;
    expect(palette.disabled).toBe(false);
    fireEvent.click(palette);
    expect(onOpenQuickOpen).toHaveBeenCalledOnce();
  });
});
