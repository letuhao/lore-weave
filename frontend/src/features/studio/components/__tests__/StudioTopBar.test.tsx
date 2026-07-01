import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { StudioTopBar } from '../StudioTopBar';

const setup = (bookTitle = 'My Book') =>
  render(
    <MemoryRouter>
      <StudioTopBar bookId="b1" bookTitle={bookTitle} />
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

  it('renders the command-palette affordance DISABLED (not a live/dead button)', () => {
    setup();
    const palette = screen.getByTestId('studio-command-palette') as HTMLButtonElement;
    expect(palette.disabled).toBe(true);
  });
});
