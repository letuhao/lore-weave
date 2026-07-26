import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { PlannerPlanView } from '../PlannerPlanView';
import type { ActionPreviewRow } from '../../actionsApi';

// Mirrors the REAL execute_plan preview rows (previewExecutePlan): human `label`, the
// concrete target in `value`, live detail in `note`, and a trailing `note`-label row.
const rows: ActionPreviewRow[] = [
  { label: 'create kinds', value: '3 new', note: '2 already exist (skipped)' },
  { label: 'delete attribute', value: 'character/hair_color', note: 'deprecates this attribute', op_id: 'op-2', destructive: true },
  { label: 'note', value: 'attribute edits cannot be planned yet' },
];

describe('PlannerPlanView', () => {
  it('renders ops as steps with label + the value target + rationale, notes separately', () => {
    render(<PlannerPlanView rows={rows} enabledOps={new Set()} onToggleOp={vi.fn()} />);
    expect(screen.getByText('Create kinds')).toBeInTheDocument();
    expect(screen.getByText('Delete attribute')).toBeInTheDocument();
    // The `value` target MUST render (the regression: it was dropped, hiding WHAT each step acts on).
    expect(screen.getByText('3 new')).toBeInTheDocument();
    expect(screen.getByText('character/hair_color')).toBeInTheDocument();
    // Rationale (note) shown.
    expect(screen.getByText(/2 already exist/)).toBeInTheDocument();
    // The trailing note is NOT a step — it renders in the notes block.
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
