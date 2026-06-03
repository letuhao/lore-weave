import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const listUserModels = vi.fn((_t: string, opts?: { capability?: string }) =>
  Promise.resolve({
    items:
      opts?.capability === 'embedding'
        ? [{ user_model_id: 'e1', alias: 'Embed-1', provider_model_name: 'bge-m3' }]
        : [{ user_model_id: 'g1', alias: 'Gen-1', provider_model_name: 'qwen' }],
  }),
);
vi.mock('@/features/settings/api', () => ({ providerApi: { listUserModels: (...a: unknown[]) => listUserModels(...a) } }));

import { ComposeConfig, type ComposeConfigValue } from '../ComposeConfig';

const V: ComposeConfigValue = { genModel: '', embedModel: '', maxSpend: '', topK: 5 };

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(ui, { wrapper: Wrapper });
}

beforeEach(() => listUserModels.mockClear());

describe('ComposeConfig', () => {
  it('renders chat + embedding model options and reports a gen-model selection', async () => {
    const onChange = vi.fn();
    wrap(<ComposeConfig value={V} onChange={onChange} />);
    await waitFor(() => expect(screen.getByRole('option', { name: 'Gen-1' })).toBeInTheDocument());
    expect(screen.getByRole('option', { name: 'Embed-1' })).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('compose-gen-model'), { target: { value: 'g1' } });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ genModel: 'g1' }));
  });

  it('reports max-spend + top-k changes', () => {
    const onChange = vi.fn();
    wrap(<ComposeConfig value={V} onChange={onChange} />);
    fireEvent.change(screen.getByTestId('compose-max-spend'), { target: { value: '0.5' } });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ maxSpend: '0.5' }));
    fireEvent.change(screen.getByTestId('compose-top-k'), { target: { value: '8' } });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ topK: 8 }));
  });

  it('shows the H0 marker (enriched-stays-a-variant cue)', () => {
    wrap(<ComposeConfig value={V} onChange={vi.fn()} />);
    expect(screen.getByTestId('enrichment-h0-marker')).toBeInTheDocument();
  });
});
