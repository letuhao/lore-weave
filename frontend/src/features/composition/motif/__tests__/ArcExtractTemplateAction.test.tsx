// S-10 O6a — "Save this arc as a template": open the inline form → type a name → POST
// /arcs/{id}/extract-template with an auto-slugified code; a 409 surfaces a rename hint.
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const apiJson = vi.fn();
vi.mock('@/api', () => ({ apiJson: (...a: unknown[]) => apiJson(...a), apiBase: () => '' }));

import { ArcExtractTemplateAction } from '../components/ArcExtractTemplateAction';
import { slugifyArcCode } from '../hooks/useArcExtractTemplate';

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

beforeEach(() => apiJson.mockReset());

describe('slugifyArcCode', () => {
  it('lowercases, collapses non-alnum to _, trims, and never empty', () => {
    expect(slugifyArcCode('  The Hero’s Fall!! ')).toBe('the_hero_s_fall');
    expect(slugifyArcCode('***')).toBe('arc');
  });
});

describe('ArcExtractTemplateAction (O6a)', () => {
  it('extracts the arc into the library with a slugified code', async () => {
    apiJson.mockResolvedValue({ id: 'T1', name: 'Revenge arc' });
    render(<ArcExtractTemplateAction nodeId="node-9" defaultName="Revenge arc" token="t" />, { wrapper: wrap() });

    fireEvent.click(screen.getByTestId('arc-extract-open'));
    // pre-filled with the arc's title
    expect((screen.getByTestId('arc-extract-name') as HTMLInputElement).value).toBe('Revenge arc');
    fireEvent.click(screen.getByTestId('arc-extract-submit'));

    await waitFor(() => expect(apiJson).toHaveBeenCalled());
    const [url, opts] = apiJson.mock.calls[0];
    expect(url).toBe('/v1/composition/arcs/node-9/extract-template');
    expect(opts.method).toBe('POST');
    expect(JSON.parse(opts.body)).toEqual({ code: 'revenge_arc', name: 'Revenge arc', visibility: 'private' });
    await waitFor(() => expect(screen.getByTestId('arc-extract-done')).toBeInTheDocument());
  });

  it('surfaces a rename hint on a 409 (duplicate code)', async () => {
    apiJson.mockRejectedValueOnce(Object.assign(new Error('conflict'), { status: 409 }));
    render(<ArcExtractTemplateAction nodeId="node-9" defaultName="Dup" token="t" />, { wrapper: wrap() });
    fireEvent.click(screen.getByTestId('arc-extract-open'));
    fireEvent.click(screen.getByTestId('arc-extract-submit'));
    await waitFor(() => expect(screen.getByTestId('arc-extract-conflict')).toBeInTheDocument());
  });

  it('cannot submit a blank name', () => {
    render(<ArcExtractTemplateAction nodeId="node-9" defaultName="" token="t" />, { wrapper: wrap() });
    fireEvent.click(screen.getByTestId('arc-extract-open'));
    expect(screen.getByTestId('arc-extract-submit')).toBeDisabled();
  });
});
