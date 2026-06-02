import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { WikiTab } from '../WikiTab';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const fetchWikiContributions = vi.fn();
vi.mock('../api', () => ({
  fetchWikiContributions: (...a: unknown[]) => fetchWikiContributions(...a),
}));

const mk = (over = {}) => ({
  article_id: 'a1', entity_id: 'e1', book_id: 'b1', display_name: 'Aldric',
  kind: { kind_id: 'k', code: 'character', name: 'Character', icon: '👤', color: '#fff' },
  status: 'published', last_contributed_at: new Date().toISOString(), ...over,
});

const renderTab = (isSelf: boolean) =>
  render(<MemoryRouter><WikiTab userId="u1" isSelf={isSelf} /></MemoryRouter>);

beforeEach(() => fetchWikiContributions.mockReset());

describe('WikiTab (UI-2a)', () => {
  it('renders contributions', async () => {
    fetchWikiContributions.mockResolvedValue({ items: [mk(), mk({ article_id: 'a2', display_name: 'Mina' })] });
    renderTab(true);
    await screen.findByText('Aldric');
    expect(screen.getByText('Mina')).toBeTruthy();
  });

  it('empty state when no contributions', async () => {
    fetchWikiContributions.mockResolvedValue({ items: [] });
    renderTab(false);
    await screen.findByText('noWiki');
  });

  it('self links to the book wiki manager; others link to the public book page', async () => {
    fetchWikiContributions.mockResolvedValue({ items: [mk()] });
    const { unmount } = renderTab(true);
    expect((await screen.findByText('Aldric')).closest('a')?.getAttribute('href')).toBe('/books/b1/wiki');
    unmount();

    fetchWikiContributions.mockResolvedValue({ items: [mk()] });
    renderTab(false);
    expect((await screen.findByText('Aldric')).closest('a')?.getAttribute('href')).toBe('/browse/b1');
  });
});
