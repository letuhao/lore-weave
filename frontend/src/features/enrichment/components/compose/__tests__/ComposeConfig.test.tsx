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

const V: ComposeConfigValue = {
  genModel: '',
  embedModel: '',
  maxSpend: '',
  topK: 5,
  technique: 'retrieval',
  requestedDimensions: null,
};

const DIMS = [
  { id: 'history', label: 'History', required: true },
  { id: 'geography', label: 'Geography', required: false },
];

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

  // #2 technique selector + #6 eval-gate warning
  it('hides the technique selector unless showTechnique', () => {
    wrap(<ComposeConfig value={V} onChange={vi.fn()} />);
    expect(screen.queryByTestId('compose-technique')).not.toBeInTheDocument();
  });

  it('shows the technique selector and reports a change when showTechnique', () => {
    const onChange = vi.fn();
    wrap(<ComposeConfig value={V} onChange={onChange} showTechnique />);
    fireEvent.change(screen.getByTestId('compose-technique'), { target: { value: 'recook' } });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ technique: 'recook' }));
  });

  it('warns about the eval-gate only for P2/P3 techniques', () => {
    const { rerender } = wrap(<ComposeConfig value={V} onChange={vi.fn()} showTechnique />);
    expect(screen.queryByTestId('compose-eval-gate-warning')).not.toBeInTheDocument(); // retrieval=P1
    rerender(<ComposeConfig value={{ ...V, technique: 'fabrication' }} onChange={vi.fn()} showTechnique />);
    expect(screen.getByTestId('compose-eval-gate-warning')).toBeInTheDocument();
  });

  // #1 dimension picker
  it('defaults to auto (no chips) and only shows chips when auto is unchecked', () => {
    const onChange = vi.fn();
    wrap(<ComposeConfig value={V} onChange={onChange} dimensions={DIMS} />);
    expect(screen.getByTestId('compose-dims-auto')).toBeChecked();
    expect(screen.queryByTestId('compose-dims-picker')).not.toBeInTheDocument();
    // unchecking auto → selects all dim ids (enrich all, explicit)
    fireEvent.click(screen.getByTestId('compose-dims-auto'));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ requestedDimensions: ['history', 'geography'] }),
    );
  });

  it('toggles a single dimension chip off → requestedDimensions excludes it', () => {
    const onChange = vi.fn();
    // start in manual mode with both selected
    wrap(
      <ComposeConfig
        value={{ ...V, requestedDimensions: ['history', 'geography'] }}
        onChange={onChange}
        dimensions={DIMS}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'History' }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ requestedDimensions: ['geography'] }),
    );
  });

  it('hides the dimension picker when no dimensions are provided', () => {
    wrap(<ComposeConfig value={V} onChange={vi.fn()} />);
    expect(screen.queryByTestId('compose-dims-auto')).not.toBeInTheDocument();
  });
});
