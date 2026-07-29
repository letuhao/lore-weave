// Batch translate — the half of the user-paid path that was engine-only.
//
// What is worth pinning here is not the happy path. The engine and the MCP tool have
// always accepted 1..50; the risk in adding a picker is all in the seams where a batch
// can quietly become a different batch than the one the user agreed to pay for:
//
//   · the count in the button must be the count that gets charged
//   · the 50-item ceiling must refuse BEFORE the estimate, not truncate after
//   · rows the caller cannot translate must be EXCLUDED and EXPLAINED, not silently
//     dropped at propose (the batch-narrowed-after-the-fact bug)
//   · results are per item — "already current, not charged" is a different fact from
//     "translated" and must not be folded into a total
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('@/api', () => ({ apiJson: vi.fn(), apiBase: () => '' }));
vi.mock('../../../campaigns/components/ModelRolePicker', () => ({
  ModelRolePicker: ({ onChange }: { onChange: (v: string) => void }) => (
    <button type="button" data-testid="pick-model" onClick={() => onChange('m-1')}>model</button>
  ),
}));

const { translatePropose, translateConfirm } = vi.hoisted(() => ({
  translatePropose: vi.fn(), translateConfirm: vi.fn(),
}));
vi.mock('../api', async (orig) => {
  const actual = await orig<typeof import('../api')>();
  return {
    ...actual,
    motifApi: { ...actual.motifApi, translatePropose, translateConfirm },
    isQuotaError: () => false,
  };
});
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_k: string, o?: { defaultValue?: string } & Record<string, unknown>) =>
      (o?.defaultValue ?? '').replace(/\{\{(\w+)\}\}/g, (_m, k) => String(o?.[k] ?? '')),
    i18n: { language: 'vi' },
  }),
}));

import { MotifBatchTranslateBar, BATCH_TRANSLATE_CAP } from '../components/MotifBatchTranslateBar';

function renderBar(props: Partial<React.ComponentProps<typeof MotifBatchTranslateBar>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MotifBatchTranslateBar
        selectedIds={['a', 'b', 'c']}
        notSelectableCount={0}
        token="t"
        onDone={() => {}}
        onCancel={() => {}}
        {...props}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  translatePropose.mockReset();
  translateConfirm.mockReset();
  translatePropose.mockResolvedValue({
    confirm_token: 'ct', descriptor: 'composition.library_translate',
    est_usd: 0.02, est_tokens: 2000, quota_remaining: null, skipped: 0,
  });
});

describe('the count the user agrees to is the count that is charged', () => {
  it('names the selection count in both the label and the button', async () => {
    renderBar();
    expect(await screen.findByTestId('motif-batch-count')).toHaveTextContent('3 selected');
    expect(screen.getByTestId('motif-batch-run')).toHaveTextContent('Translate 3');
  });

  it('sends exactly the selected ids', async () => {
    renderBar();
    fireEvent.click(screen.getByTestId('pick-model'));
    fireEvent.click(screen.getByTestId('motif-batch-run'));
    await screen.findByTestId('motif-cost-confirm');
    expect(translatePropose.mock.calls[0][0].ids).toEqual(['a', 'b', 'c']);
  });

  it('refuses OVER the cap before estimating, rather than truncating after', async () => {
    // The engine caps server-side either way. Discovering that after paying is the bad
    // version, so the refusal is stated with the ceiling and the overage named.
    renderBar({ selectedIds: Array.from({ length: BATCH_TRANSLATE_CAP + 3 }, (_, i) => `m${i}`) });
    const warn = await screen.findByTestId('motif-batch-over-cap');
    expect(warn).toHaveTextContent(String(BATCH_TRANSLATE_CAP));
    expect(warn).toHaveTextContent('deselect 3');
    fireEvent.click(screen.getByTestId('pick-model'));
    expect(screen.getByTestId('motif-batch-run')).toBeDisabled();
    expect(translatePropose).not.toHaveBeenCalled();
  });

  it('cannot run with nothing selected', async () => {
    renderBar({ selectedIds: [] });
    fireEvent.click(await screen.findByTestId('pick-model'));
    expect(screen.getByTestId('motif-batch-run')).toBeDisabled();
  });

  it('cannot run without a model — the spend is the USER\'s model, not a platform default', async () => {
    renderBar();
    expect(await screen.findByTestId('motif-batch-run')).toBeDisabled();
  });
});

describe('what is excluded is explained', () => {
  it('says how many rows are not the caller\'s to translate, and why', async () => {
    renderBar({ notSelectableCount: 12 });
    const note = await screen.findByTestId('motif-batch-excluded');
    expect(note).toHaveTextContent('12 not yours to translate');
    expect(note).toHaveTextContent(/built-ins are already free/i);
  });

  it('says nothing when everything on screen is selectable', async () => {
    renderBar({ notSelectableCount: 0 });
    await screen.findByTestId('motif-batch-count');
    expect(screen.queryByTestId('motif-batch-excluded')).toBeNull();
  });

  it('surfaces a server-side narrowing on the confirm card', async () => {
    // Belt and braces: the UI only offers translatable rows, but the server filters
    // again (ownership can change between render and propose). If it drops any, the
    // quote must say so rather than charging for a smaller batch in silence.
    translatePropose.mockResolvedValue({
      confirm_token: 'ct', descriptor: 'composition.library_translate',
      est_usd: 0.01, est_tokens: 900, quota_remaining: null, skipped: 2,
    });
    renderBar();
    fireEvent.click(screen.getByTestId('pick-model'));
    fireEvent.click(screen.getByTestId('motif-batch-run'));
    expect(await screen.findByTestId('motif-batch-skipped')).toHaveTextContent('2 of the motifs');
  });
});

describe('results are per item, not a total', () => {
  it('breaks the outcome down and keeps "not charged" distinguishable from "translated"', async () => {
    translateConfirm.mockResolvedValue({
      kind: 'motif', target_language: 'vi', requested: 4, written: 2,
      results: [
        { id: 'a', status: 'translated', echoed: [] },
        { id: 'b', status: 'translated', echoed: ['summary'] },
        { id: 'c', status: 'already_translated' },
        { id: 'd', status: 'authored_kept' },
      ],
    });
    renderBar({ selectedIds: ['a', 'b', 'c', 'd'] });
    fireEvent.click(screen.getByTestId('pick-model'));
    fireEvent.click(screen.getByTestId('motif-batch-run'));
    fireEvent.click(await screen.findByTestId('motif-cost-confirm-btn'));

    const res = await screen.findByTestId('motif-batch-result');
    expect(res).toHaveTextContent('2 of 4 translated');
    // The two that cost nothing are named, not absorbed into the total.
    expect(screen.getByTestId('motif-batch-outcome-already_translated')).toBeInTheDocument();
    expect(screen.getByTestId('motif-batch-outcome-authored_kept')).toBeInTheDocument();
    // …and an echo anywhere in the batch is reported, since we deliberately do not
    // re-spend to retry it.
    expect(screen.getByTestId('motif-batch-echoed')).toHaveTextContent('1 field(s)');
  });

  it('reports a failure instead of a silent no-op', async () => {
    translateConfirm.mockRejectedValue(new Error('provider exploded'));
    renderBar();
    fireEvent.click(screen.getByTestId('pick-model'));
    fireEvent.click(screen.getByTestId('motif-batch-run'));
    fireEvent.click(await screen.findByTestId('motif-cost-confirm-btn'));
    expect(await screen.findByTestId('motif-batch-error')).toHaveTextContent('provider exploded');
  });
});
