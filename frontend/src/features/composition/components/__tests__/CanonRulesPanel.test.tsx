import { render, screen, fireEvent, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CanonRulesPanel } from '../CanonRulesPanel';
import type { CanonRule } from '../../types';

// FD-16 — mock the data hooks; assert the panel sends the FULL payload on create
// (entity/reveal-window/active, the old gap) and wires the previously-unused
// `patch` for edit-in-place.
const { canon, roster, toastFn, toastError } = vi.hoisted(() => ({
  canon: {
    list: { isLoading: false, data: [] as CanonRule[] },
    create: { mutate: vi.fn(), isPending: false },
    patch: { mutate: vi.fn(), isPending: false },
    remove: { mutate: vi.fn() },
    restore: { mutate: vi.fn() },
  },
  roster: { data: [{ id: 'e1', label: 'Kael' }], isLoading: false },
  toastFn: vi.fn(),
  toastError: vi.fn(),
}));
vi.mock('../../hooks/useCanonRules', () => ({ useCanonRules: () => canon }));
vi.mock('../../hooks/useGlossaryRoster', () => ({ useGlossaryRoster: () => roster }));
vi.mock('sonner', () => ({ toast: Object.assign(toastFn, { error: toastError }) }));

function rule(over: Partial<CanonRule>): CanonRule {
  return {
    id: 'r1', text: 'no magic', scope: 'world', entity_id: null,
    from_order: null, until_order: null, active: true, version: 1, ...over,
  };
}

beforeEach(() => {
  canon.list = { isLoading: false, data: [] };
  canon.create.mutate.mockClear();
  canon.patch.mutate.mockClear();
  canon.remove.mutate.mockClear();
  canon.restore.mutate.mockClear();
  toastFn.mockClear();
  toastError.mockClear();
});

describe('CanonRulesPanel (FD-16)', () => {
  it('create sends the full payload including the reveal window', () => {
    render(<CanonRulesPanel projectId="p" bookId="b" token="t" />);
    fireEvent.change(screen.getByTestId('composition-canon-input'), { target: { value: 'Hidden heir' } });
    fireEvent.change(screen.getByTestId('composition-canon-scope'), { target: { value: 'reveal_gate' } });
    fireEvent.change(screen.getByTestId('composition-canon-from'), { target: { value: '5' } });
    fireEvent.change(screen.getByTestId('composition-canon-until'), { target: { value: '12' } });
    fireEvent.change(screen.getByTestId('composition-canon-entity'), { target: { value: 'e1' } });
    fireEvent.click(screen.getByTestId('composition-canon-submit'));

    expect(canon.create.mutate).toHaveBeenCalledTimes(1);
    expect(canon.create.mutate.mock.calls[0][0]).toMatchObject({
      text: 'Hidden heir', scope: 'reveal_gate',
      entity_id: 'e1', from_order: 5, until_order: 12, active: true,
    });
  });

  it('drops entity/window for world scope', () => {
    render(<CanonRulesPanel projectId="p" bookId="b" token="t" />);
    fireEvent.change(screen.getByTestId('composition-canon-input'), { target: { value: 'world rule' } });
    // scope defaults to 'world' → no entity/from/until fields rendered
    expect(screen.queryByTestId('composition-canon-entity')).toBeNull();
    expect(screen.queryByTestId('composition-canon-from')).toBeNull();
    fireEvent.click(screen.getByTestId('composition-canon-submit'));
    expect(canon.create.mutate.mock.calls[0][0]).toMatchObject({
      scope: 'world', entity_id: null, from_order: null, until_order: null,
    });
  });

  it('blocks an inverted reveal window (submit disabled + error)', () => {
    render(<CanonRulesPanel projectId="p" bookId="b" token="t" />);
    fireEvent.change(screen.getByTestId('composition-canon-input'), { target: { value: 'x' } });
    fireEvent.change(screen.getByTestId('composition-canon-scope'), { target: { value: 'reveal_gate' } });
    fireEvent.change(screen.getByTestId('composition-canon-from'), { target: { value: '12' } });
    fireEvent.change(screen.getByTestId('composition-canon-until'), { target: { value: '5' } });

    expect(screen.getByTestId('composition-canon-window-error')).toBeTruthy();
    expect((screen.getByTestId('composition-canon-submit') as HTMLButtonElement).disabled).toBe(true);
  });

  it('edits a rule in place via the patch hook (carrying its version)', () => {
    canon.list = { isLoading: false, data: [rule({ id: 'r1', text: 'old', version: 3 })] };
    render(<CanonRulesPanel projectId="p" bookId="b" token="t" />);

    fireEvent.click(screen.getByTestId('composition-canon-edit'));
    const li = screen.getByTestId('composition-canon-rule');
    fireEvent.change(within(li).getByTestId('composition-canon-input'), { target: { value: 'updated' } });
    fireEvent.click(within(li).getByTestId('composition-canon-submit'));

    expect(canon.patch.mutate).toHaveBeenCalledTimes(1);
    const [arg] = canon.patch.mutate.mock.calls[0];
    expect(arg.id).toBe('r1');
    expect(arg.version).toBe(3);
    expect(arg.payload).toMatchObject({ text: 'updated' });
  });

  it('edit→world scope sends EXPLICIT nulls so the BE clears stale bounds', () => {
    // The BE patch uses exclude_unset + only clears entity_id/from/until when
    // they are PRESENT-and-null. The form must send explicit nulls (not omit) on
    // a reveal_gate→world change, else stale bounds silently persist.
    canon.list = {
      isLoading: false,
      data: [rule({ id: 'r1', scope: 'reveal_gate', entity_id: 'e1', from_order: 2, until_order: 9, version: 4 })],
    };
    render(<CanonRulesPanel projectId="p" bookId="b" token="t" />);
    fireEvent.click(screen.getByTestId('composition-canon-edit'));
    const li = screen.getByTestId('composition-canon-rule');
    fireEvent.change(within(li).getByTestId('composition-canon-scope'), { target: { value: 'world' } });
    fireEvent.click(within(li).getByTestId('composition-canon-submit'));

    const [arg] = canon.patch.mutate.mock.calls[0];
    expect(arg.payload.scope).toBe('world');
    expect(arg.payload).toHaveProperty('entity_id', null);
    expect(arg.payload).toHaveProperty('from_order', null);
    expect(arg.payload).toHaveProperty('until_order', null);
  });

  it('edit toggles back to the read view on cancel', () => {
    canon.list = { isLoading: false, data: [rule({ id: 'r1' })] };
    render(<CanonRulesPanel projectId="p" bookId="b" token="t" />);
    fireEvent.click(screen.getByTestId('composition-canon-edit'));
    const li = screen.getByTestId('composition-canon-rule');
    fireEvent.click(within(li).getByTestId('composition-canon-cancel'));
    // back to view → the edit affordance is shown again, no form input
    expect(screen.getByTestId('composition-canon-edit')).toBeTruthy();
    expect(within(screen.getByTestId('composition-canon-rule')).queryByTestId('composition-canon-input')).toBeNull();
  });

  it('archives a rule (with an error handler — never a silent swallow)', () => {
    canon.list = { isLoading: false, data: [rule({ id: 'r9' })] };
    render(<CanonRulesPanel projectId="p" bookId="b" token="t" />);
    fireEvent.click(screen.getByTestId('composition-canon-archive'));
    const [id, opts] = canon.remove.mutate.mock.calls[0];
    expect(id).toBe('r9');
    // BE-11 fix: the delete used to have NO onError, so a failed archive was silently swallowed.
    expect(opts.onError).toBeTypeOf('function');
    opts.onError(new Error('boom'));
    expect(toastError).toHaveBeenCalled();
  });

  it('archive success offers an Undo that restores the rule (BE-11)', () => {
    canon.list = { isLoading: false, data: [rule({ id: 'r9' })] };
    render(<CanonRulesPanel projectId="p" bookId="b" token="t" />);
    fireEvent.click(screen.getByTestId('composition-canon-archive'));
    const [, opts] = canon.remove.mutate.mock.calls[0];
    // DELETE is a soft-archive returning the archived row; the toast holds its id.
    opts.onSuccess({ id: 'r9' });
    expect(toastFn).toHaveBeenCalled();
    const toastOpts = toastFn.mock.calls[0][1];
    toastOpts.action.onClick();
    expect(canon.restore.mutate).toHaveBeenCalledWith('r9', expect.anything());
  });

  it('offers a Show-archived toggle (BE-11b)', () => {
    render(<CanonRulesPanel projectId="p" bookId="b" token="t" />);
    expect(screen.getByTestId('composition-canon-show-archived')).toBeTruthy();
  });

  it('an archived rule shows Restore — never Edit/Archive — and restores on click', () => {
    canon.list = { isLoading: false, data: [rule({ id: 'r7', is_archived: true })] };
    render(<CanonRulesPanel projectId="p" bookId="b" token="t" />);
    expect(screen.getByTestId('composition-canon-restore')).toBeTruthy();
    expect(screen.queryByTestId('composition-canon-edit')).toBeNull();
    expect(screen.queryByTestId('composition-canon-archive')).toBeNull();
    fireEvent.click(screen.getByTestId('composition-canon-restore'));
    expect(canon.restore.mutate).toHaveBeenCalledWith('r7', expect.anything());
  });
});
