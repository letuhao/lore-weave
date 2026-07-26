// S-10 O6c — "Group my chapters into arcs": a confirm step (it writes an arc layer) → POST
// /books/{id}/arcs/decompile → a summary of what landed. Idempotent, so re-clicking is safe.
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const apiJson = vi.fn();
vi.mock('@/api', () => ({ apiJson: (...a: unknown[]) => apiJson(...a), apiBase: () => '' }));

import { DecompileArcsAction } from '../components/DecompileArcsAction';

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

beforeEach(() => apiJson.mockReset());

describe('DecompileArcsAction (O6c)', () => {
  it('confirms, then groups chapters into arcs and reports what landed', async () => {
    apiJson.mockResolvedValue({ arcs: 3, chapters_assigned: 24, arc_ids: ['a', 'b', 'c'] });
    render(<DecompileArcsAction bookId="book-9" token="t" />, { wrapper: wrap() });

    // the primary button asks for confirmation first (it writes an arc layer)
    fireEvent.click(screen.getByTestId('decompile-open'));
    expect(screen.getByTestId('decompile-confirm')).toBeInTheDocument();
    expect(apiJson).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('decompile-run'));
    await waitFor(() => expect(apiJson).toHaveBeenCalled());
    const [url, opts] = apiJson.mock.calls[0];
    expect(url).toBe('/v1/composition/books/book-9/arcs/decompile');
    expect(opts.method).toBe('POST');
    expect(JSON.parse(opts.body)).toEqual({ chapters_per_arc: 10 });

    // i18n is mocked to return keys in tests, so assert the success branch's key (not the interpolation).
    await waitFor(() => expect(screen.getByTestId('decompile-done')).toHaveTextContent('motif.arc.decompile.done'));
  });

  it('cancel backs out without calling the engine', () => {
    render(<DecompileArcsAction bookId="book-9" token="t" />, { wrapper: wrap() });
    fireEvent.click(screen.getByTestId('decompile-open'));
    fireEvent.click(screen.getByTestId('decompile-cancel'));
    expect(screen.queryByTestId('decompile-confirm')).toBeNull();
    expect(apiJson).not.toHaveBeenCalled();
  });

  it('reports the no-op case (a book with nothing to group)', async () => {
    apiJson.mockResolvedValue({ arcs: 0, chapters_assigned: 0, arc_ids: [] });
    render(<DecompileArcsAction bookId="book-9" token="t" />, { wrapper: wrap() });
    fireEvent.click(screen.getByTestId('decompile-open'));
    fireEvent.click(screen.getByTestId('decompile-run'));
    // the arcs===0 branch renders the "none" key (i18n mocked to keys).
    await waitFor(() => expect(screen.getByTestId('decompile-done')).toHaveTextContent('motif.arc.decompile.none'));
  });

  it('renders nothing without a book', () => {
    const { container } = render(<DecompileArcsAction bookId={null} token="t" />, { wrapper: wrap() });
    expect(container).toBeEmptyDOMElement();
  });
});
