// WI-1 (D-MOTIF-MINE-FE-BRIDGE) — the mining panel wiring + the mint→confirm→poll hook.
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

// ModelRolePicker fetches BYOK models — stub it to a simple select so the panel test is
// hermetic (it just needs to drive `value`/`onChange`).
vi.mock('../../../campaigns/components/ModelRolePicker', () => ({
  ModelRolePicker: ({ value, onChange }: { value: string | null; onChange: (v: string) => void }) => (
    <button data-testid="pick-model" onClick={() => onChange('model-1')}>{value ?? 'pick'}</button>
  ),
}));

import { motifApi } from '../api';
import { MotifMinePanel } from '../components/MotifMinePanel';
import { useMotifMine } from '../hooks/useMotifMine';

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('MotifMinePanel', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('mints with the picked model, then shows the cost-confirm', async () => {
    const propose = vi.spyOn(motifApi, 'minePropose').mockResolvedValue({
      confirm_token: 'tok', descriptor: 'composition.motif_mine',
      est_usd: 0.5, est_tokens: 0, quota_remaining: null,
    });
    wrap(<MotifMinePanel token="t" />);
    fireEvent.click(screen.getByTestId('pick-model'));           // select a model
    fireEvent.click(screen.getByTestId('motif-mine-run-btn'));   // mint
    await waitFor(() => expect(propose).toHaveBeenCalledTimes(1));
    // corpus is the default scope when no bookId is given
    expect(propose.mock.calls[0][0]).toMatchObject({ scope: 'corpus', modelRef: 'model-1' });
    // the cost-confirm card appears once the estimate is minted
    await screen.findByText(/0\.5|metered/i);
  });

  it('book scope is disabled without a bookId, enabled with one', () => {
    const { rerender } = wrap(<MotifMinePanel token="t" />);
    expect(screen.getByTestId('motif-mine-scope-book')).toBeDisabled();
    const qc = new QueryClient();
    rerender(<QueryClientProvider client={qc}><MotifMinePanel token="t" bookId="b1" /></QueryClientProvider>);
    expect(screen.getByTestId('motif-mine-scope-book')).not.toBeDisabled();
  });
});

describe('useMotifMine flow', () => {
  it('mint → confirm returns the MineResult and invalidates the motif lists', async () => {
    vi.spyOn(motifApi, 'minePropose').mockResolvedValue({
      confirm_token: 'tok', descriptor: 'composition.motif_mine',
      est_usd: 0.5, est_tokens: 0, quota_remaining: null,
    });
    vi.spyOn(motifApi, 'mineConfirm').mockResolvedValue({ mined: 2, motif_ids: ['a', 'b'], below_gate: 1 });

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(qc, 'invalidateQueries');
    let hook!: ReturnType<typeof useMotifMine>;
    function Probe() { hook = useMotifMine('t'); return null; }
    render(<QueryClientProvider client={qc}><Probe /></QueryClientProvider>);

    await hook.mint.mutateAsync('model-1');
    expect(hook.estimate?.confirm_token).toBe('tok');
    await hook.confirm.mutateAsync();
    await waitFor(() => expect(hook.result?.mined).toBe(2));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['composition', 'motifs'] });
  });
});
