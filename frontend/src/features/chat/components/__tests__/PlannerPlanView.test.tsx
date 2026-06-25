import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { PlannerPlanView } from '../PlannerPlanView';
import type { ActionPreviewRow } from '../../actionsApi';

const rows: ActionPreviewRow[] = [
  { label: 'create_kinds', value: 'op-1', note: 'add vampire_hunter, asylum kinds' },
  { label: 'delete_kind', value: 'op-2', note: 'remove the deity kind', op_id: 'op-2', destructive: true },
  { label: 'note', value: 'attribute edits cannot be planned yet' },
];

describe('PlannerPlanView', () => {
  it('renders ops as numbered steps with humanized labels + rationale, and notes separately', () => {
    render(<PlannerPlanView rows={rows} enabledOps={new Set()} onToggleOp={vi.fn()} />);
    // Humanized op labels (not the raw snake_case type).
    expect(screen.getByText('Create kinds')).toBeInTheDocument();
    expect(screen.getByText('Delete kind')).toBeInTheDocument();
    // Rationale shown.
    expect(screen.getByText(/add vampire_hunter/)).toBeInTheDocument();
    // The note is NOT a step — it renders in the notes block.
    expect(screen.getByText(/attribute edits cannot be planned yet/)).toBeInTheDocument();
  });

  it('destructive op renders a default-OFF opt-in checkbox; toggling fires onToggleOp', () => {
    const onToggleOp = vi.fn();
    render(<PlannerPlanView rows={rows} enabledOps={new Set()} onToggleOp={onToggleOp} />);
    const box = screen.getByTestId('enable-op') as HTMLInputElement;
    expect(box.checked).toBe(false); // default OFF (G1)
    expect(box.getAttribute('data-op-id')).toBe('op-2');
    fireEvent.click(box);
    expect(onToggleOp).toHaveBeenCalledWith('op-2');
  });

  it('only destructive ops get a checkbox (non-destructive create_kinds has none)', () => {
    render(<PlannerPlanView rows={rows} enabledOps={new Set()} onToggleOp={vi.fn()} />);
    // exactly one enable-op checkbox (for the one destructive op).
    expect(screen.getAllByTestId('enable-op')).toHaveLength(1);
  });

  it('reflects an already-enabled op as checked', () => {
    render(<PlannerPlanView rows={rows} enabledOps={new Set(['op-2'])} onToggleOp={vi.fn()} />);
    expect((screen.getByTestId('enable-op') as HTMLInputElement).checked).toBe(true);
  });
});
