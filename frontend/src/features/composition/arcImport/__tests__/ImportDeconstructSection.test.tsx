// 34 §4.3 拆文 — the section enforces the paid-action guards: an over-length paste can't submit, the
// deconstruct is IMPOSSIBLE without an explicit model (AT-8), and a failure surfaces verbatim (never
// a spinner-forever — the confirm-500 hazard). Driven by a mock controller + stubbed model/cost card.
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

const ctrl = vi.hoisted(() => ({ useDeconstruct: vi.fn() }));
vi.mock('../useDeconstruct', async () => ({ useDeconstruct: ctrl.useDeconstruct, IMPORT_SOURCE_MAX: 20000 }));
vi.mock('../../motif/components/CostConfirmCard', () => ({
  CostConfirmCard: (p: { onConfirm: () => void; onCancel: () => void }) => (
    <div data-testid="cost-card"><button data-testid="cost-confirm" onClick={p.onConfirm}>confirm</button></div>
  ),
}));
let modelOnChange: ((v: string | null) => void) | null = null;
vi.mock('../../../campaigns/components/ModelRolePicker', () => ({
  ModelRolePicker: (p: { onChange: (v: string | null) => void }) => { modelOnChange = p.onChange; return <div data-testid="model-picker" />; },
}));

import { ImportDeconstructSection } from '../ImportDeconstructSection';

function makeD(over: Partial<Record<string, unknown>> = {}) {
  return {
    sources: [{ id: 's1', title: 'Ref', created_at: '' }], sourcesLoading: false, sourcesError: false,
    selectedSourceId: 's1', setSelectedSourceId: vi.fn(), arcHint: '', setArcHint: vi.fn(),
    useWeb: false, setUseWeb: vi.fn(), language: 'en', setLanguage: vi.fn(),
    createSource: { mutate: vi.fn(), isPending: false, isError: false, error: null },
    deleteSource: { mutate: vi.fn(), isError: false, error: null },
    estimate: null, result: null,
    mint: { mutate: vi.fn(), isPending: false, isError: false },
    confirm: { mutate: vi.fn(), isPending: false, isError: false },
    cancel: vi.fn(), reset: vi.fn(), error: null, ...over,
  };
}

beforeEach(() => { ctrl.useDeconstruct.mockReset(); modelOnChange = null; });

describe('ImportDeconstructSection', () => {
  it('states the B-3 copyright, not buried', () => {
    ctrl.useDeconstruct.mockReturnValue(makeD());
    render(<ImportDeconstructSection token="tok" />);
    // (the test i18n returns the key, not the English copy — assert the notice IS rendered)
    expect(screen.getByTestId('deconstruct-copyright')).toBeInTheDocument();
  });

  it('an over-length paste blocks Add source', () => {
    ctrl.useDeconstruct.mockReturnValue(makeD());
    render(<ImportDeconstructSection token="tok" />);
    fireEvent.change(screen.getByTestId('paste-title'), { target: { value: 't' } });
    fireEvent.change(screen.getByTestId('paste-content'), { target: { value: 'x'.repeat(20001) } });
    expect(screen.getByTestId('paste-over')).toBeInTheDocument();
    expect(screen.getByTestId('paste-submit')).toBeDisabled();
  });

  it('AT-8: Deconstruct is impossible without an explicit model', () => {
    const d = makeD();
    ctrl.useDeconstruct.mockReturnValue(d);
    render(<ImportDeconstructSection token="tok" />);
    // no model chosen → disabled
    expect(screen.getByTestId('deconstruct-run')).toBeDisabled();
    // choose a model → enabled → clicking mints with THAT model (no silent platform payer)
    act(() => modelOnChange?.('gemma-user-model'));
    expect(screen.getByTestId('deconstruct-run')).not.toBeDisabled();
    fireEvent.click(screen.getByTestId('deconstruct-run'));
    expect(d.mint.mutate).toHaveBeenCalledWith('gemma-user-model');
  });

  it('an estimate renders the cost card (spend NOT yet happened); confirm commits', () => {
    const d = makeD({ estimate: { confirm_token: 'ct', est_usd: 0, est_tokens: 0, descriptor: 'composition.arc_import', quota_remaining: null } });
    ctrl.useDeconstruct.mockReturnValue(d);
    render(<ImportDeconstructSection token="tok" />);
    expect(screen.getByTestId('cost-card')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('cost-confirm'));
    expect(d.confirm.mutate).toHaveBeenCalled();
  });

  it('a failure surfaces verbatim — never a spinner-forever (the confirm-500 hazard)', () => {
    ctrl.useDeconstruct.mockReturnValue(makeD({ error: new Error('deconstruct was not accepted') }));
    render(<ImportDeconstructSection token="tok" />);
    expect(screen.getByTestId('deconstruct-error').textContent).toContain('not accepted');
  });

  it('a source create/delete error is SURFACED, not silent (no-silent-fail)', () => {
    ctrl.useDeconstruct.mockReturnValue(makeD({ createSource: { mutate: vi.fn(), isPending: false, isError: true, error: new Error('source too long') } }));
    render(<ImportDeconstructSection token="tok" />);
    expect(screen.getByTestId('deconstruct-source-error').textContent).toContain('source too long');
  });

  it('deleting a source is guarded by a confirm (hard delete, no restore)', () => {
    const d = makeD();
    ctrl.useDeconstruct.mockReturnValue(d);
    render(<ImportDeconstructSection token="tok" />);
    const confirmSpy = vi.spyOn(window, 'confirm');
    confirmSpy.mockReturnValueOnce(false);   // user cancels → no delete
    fireEvent.click(screen.getByTestId('source-del-s1'));
    expect(d.deleteSource.mutate).not.toHaveBeenCalled();
    confirmSpy.mockReturnValueOnce(true);    // user confirms → delete fires
    fireEvent.click(screen.getByTestId('source-del-s1'));
    expect(d.deleteSource.mutate).toHaveBeenCalledWith('s1');
    confirmSpy.mockRestore();
  });
});
