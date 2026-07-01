import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { StudioTopBar } from '../StudioTopBar';

const setup = (bookTitle = 'My Book', onOpenQuickOpen = vi.fn()) =>
  render(
    <MemoryRouter>
      <StudioTopBar bookId="b1" bookTitle={bookTitle} onOpenQuickOpen={onOpenQuickOpen} />
    </MemoryRouter>,
  );

describe('StudioTopBar', () => {
  it('shows the studio title + book title', () => {
    setup('Ma Nữ Nghịch Thiên');
    expect(screen.getByText('title')).toBeTruthy(); // studio title key
    expect(screen.getByText('Ma Nữ Nghịch Thiên')).toBeTruthy();
  });

  it('links back to the book and to settings', () => {
    setup();
    const hrefs = screen.getAllByRole('link').map((a) => a.getAttribute('href'));
    expect(hrefs).toContain('/books/b1');
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
