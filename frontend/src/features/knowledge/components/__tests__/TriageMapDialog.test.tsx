import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }) }));

const useResolvedSchemaMock = vi.fn();
vi.mock('../../hooks/useResolvedSchema', () => ({
  useResolvedSchema: (...a: unknown[]) => useResolvedSchemaMock(...a),
}));

import { TriageMapDialog } from '../TriageMapDialog';

describe('TriageMapDialog (S-05b F4 — code select, no raw prompt)', () => {
  beforeEach(() => {
    useResolvedSchemaMock.mockReset();
    useResolvedSchemaMock.mockReturnValue({
      schema: {
        edge_types: [{ code: 'rules_over' }, { code: 'allied_with' }],
        node_kinds: [{ code: 'person' }],
        vocab_values: { drive: [{ code: 'curiosity' }] },
      },
    });
  });

  it('lists EDGE-TYPE codes for an unknown_edge_type + maps onto the picked one', () => {
    const onPick = vi.fn();
    render(
      <TriageMapDialog open onOpenChange={vi.fn()} projectId="p-1"
        itemType="unknown_edge_type" payload={{ predicate: 'reigns' }} onPick={onPick} />,
    );
    const select = screen.getByTestId('triage-map-select') as HTMLSelectElement;
    const opts = Array.from(select.querySelectorAll('option')).map((o) => o.value);
    expect(opts).toEqual(['', 'rules_over', 'allied_with']); // '' = keep detected
    fireEvent.change(select, { target: { value: 'allied_with' } });
    fireEvent.click(screen.getByTestId('triage-map-confirm'));
    expect(onPick).toHaveBeenCalledWith('allied_with');
  });

  it('lists the SET vocab codes for an unknown_vocab_value (keyed by payload.set_code)', () => {
    render(
      <TriageMapDialog open onOpenChange={vi.fn()} projectId="p-1"
        itemType="unknown_vocab_value" payload={{ set_code: 'drive', value: 'wonder' }} onPick={vi.fn()} />,
    );
    const opts = Array.from(
      (screen.getByTestId('triage-map-select') as HTMLSelectElement).querySelectorAll('option'),
    ).map((o) => o.value);
    expect(opts).toEqual(['', 'curiosity']);
  });

  it('keep-detected (blank) → onPick(null)', () => {
    const onPick = vi.fn();
    render(
      <TriageMapDialog open onOpenChange={vi.fn()} projectId="p-1"
        itemType="unknown_edge_type" payload={{}} onPick={onPick} />,
    );
    fireEvent.click(screen.getByTestId('triage-map-confirm')); // default '' selected
    expect(onPick).toHaveBeenCalledWith(null);
  });
});
