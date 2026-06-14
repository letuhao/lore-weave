import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import '@/i18n';

// C22 — the Translate intent must land on a TAILORED books surface (a translation
// hint), not a generic shell. This locks that ?intent=translate is consumed, so a
// regression to "Write and Translate are identical" is caught by the suite.

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

vi.mock('@/features/books/api', () => ({
  booksApi: { listBooks: vi.fn().mockResolvedValue({ items: [], total: 0 }) },
}));
vi.mock('@/features/translation/api', () => ({
  translationApi: { getBookCoverage: vi.fn().mockResolvedValue({ target_languages: [] }) },
}));

import { BooksPage } from '../BooksPage';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <BooksPage />
    </MemoryRouter>,
  );
}

describe('BooksPage translate-intent (C22)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows the translation hint when routed with ?intent=translate (tailored surface)', async () => {
    renderAt('/books?intent=translate');
    await waitFor(() => expect(screen.getByTestId('translate-intent-hint')).toBeInTheDocument());
  });

  it('does NOT show the translation hint on the plain Write landing (/books)', async () => {
    renderAt('/books');
    // let the mount settle (the create button is always present once rendered)
    await waitFor(() => expect(screen.getByTestId('book-create-button')).toBeInTheDocument());
    expect(screen.queryByTestId('translate-intent-hint')).not.toBeInTheDocument();
  });
});
