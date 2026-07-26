// W10 arc-timeline — the arc-template library surface: lists the caller's visible arcs;
// selecting one opens the timeline editor + apply-preview; back returns to the list.
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const apiJson = vi.fn();
vi.mock('@/api', () => ({ apiJson: (...a: unknown[]) => apiJson(...a), apiBase: () => '' }));

import { ArcTemplateLibraryView } from '../components/ArcTemplateLibraryView';
import type { ArcTemplate } from '../arcTypes';

const ARC: ArcTemplate = {
  id: 'A1', owner_user_id: 'u1', code: 'rev', language: 'en', visibility: 'private',
  name: 'Revenge Spiral', summary: '', genre_tags: ['xianxia'], chapter_span: 12,
  threads: [{ key: 'combat', label: 'Combat' }],
  layout: [{ motif_code: 'duel', motif_id: 'm1', thread: 'combat', span_start: 2, span_end: 3, ord: 0 }],
  pacing: [], arc_roster: [], source: 'authored', imported_derived: false,
  source_version: null, status: 'active', version: 1,
};

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  apiJson.mockReset();
  localStorage.setItem('lw_user', JSON.stringify({ user_id: 'u1' }));
  apiJson.mockImplementation((url: string) => {
    if (url.includes('/arc-templates/A1')) return Promise.resolve(ARC);          // GET one (editor)
    if (url.includes('/arc-templates')) return Promise.resolve({ arc_templates: [ARC], scope: 'all', limit: 100 });
    return Promise.resolve({});
  });
});

describe('ArcTemplateLibraryView', () => {
  it('lists the caller’s arc templates with a tier badge', async () => {
    render(<ArcTemplateLibraryView token="tok" />, { wrapper: wrap() });
    expect(await screen.findByTestId('arc-row-A1')).toBeInTheDocument();
    expect(screen.getByText('Revenge Spiral')).toBeInTheDocument();
    expect(screen.getByTestId('arc-tier-A1')).toBeInTheDocument();
  });

  it('selecting an arc opens the timeline editor + apply-preview; back returns to the list', async () => {
    render(<ArcTemplateLibraryView token="tok" />, { wrapper: wrap() });
    fireEvent.click(await screen.findByTestId('arc-row-A1'));
    expect(await screen.findByTestId('arc-template-detail')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('arc-timeline-editor')).toBeInTheDocument());
    expect(screen.getByTestId('arc-apply-preview')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('arc-back'));
    expect(await screen.findByTestId('arc-row-A1')).toBeInTheDocument();
  });

  it('renders an empty state when the caller has no arcs', async () => {
    apiJson.mockReset();
    apiJson.mockResolvedValue({ arc_templates: [], scope: 'all', limit: 100 });
    render(<ArcTemplateLibraryView token="tok" />, { wrapper: wrap() });
    expect(await screen.findByTestId('arc-library-empty')).toBeInTheDocument();
  });
});
