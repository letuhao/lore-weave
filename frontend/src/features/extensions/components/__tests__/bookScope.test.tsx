// D-REG-BOOK-TIER-FE — when a book is scoped, the capability hooks LIST that book's
// rows (book_id param) and CREATE book-tier (tier:'book' + book_id). EFFECT-asserted
// through SubagentsView (the pattern is identical across all 5 capabilities).
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'test-token' }) }));
// Pin the scope to a book so the hook injects it (no BookPicker interaction needed).
vi.mock('@/features/extensions/context/ExtensionScope', () => ({
  useExtensionScope: () => ({ bookId: 'book-1', setBookId: () => {} }),
  ExtensionScopeProvider: ({ children }: { children: React.ReactNode }) => children,
}));

const api = vi.hoisted(() => ({
  listSubagents: vi.fn(),
  createSubagent: vi.fn(),
  patchSubagent: vi.fn(),
  deleteSubagent: vi.fn(),
}));
vi.mock('@/features/extensions/api', () => ({ extensionsApi: api }));

import { SubagentsView } from '../SubagentsView';

beforeEach(() => {
  Object.values(api).forEach((f) => (f as ReturnType<typeof vi.fn>).mockReset());
  api.listSubagents.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
});

describe('book-scoped extensions (SubagentsView)', () => {
  it('lists with the scoped book_id', async () => {
    render(<SubagentsView />);
    await waitFor(() => expect(api.listSubagents).toHaveBeenCalled());
    expect(api.listSubagents.mock.calls[0][1]).toMatchObject({ book_id: 'book-1' });
  });

  it('creates book-tier (tier:book + book_id) when a book is scoped', async () => {
    api.createSubagent.mockResolvedValue({});
    render(<SubagentsView />);
    await waitFor(() => expect(screen.getByTestId('sa-name')).toBeTruthy());
    fireEvent.change(screen.getByTestId('sa-name'), { target: { value: 'book-scout' } });
    fireEvent.change(screen.getByTestId('sa-prompt'), { target: { value: 'p' } });
    fireEvent.click(screen.getByTestId('sa-create'));
    await waitFor(() => expect(api.createSubagent).toHaveBeenCalled());
    expect(api.createSubagent.mock.calls[0][1]).toMatchObject({ name: 'book-scout', tier: 'book', book_id: 'book-1' });
  });
});
