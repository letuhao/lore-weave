import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// EDIT-ATOMIC — the edit-existing diff card: renders N old→new rows from
// `changes[]` and Apply issues ONE atomic apply-edit (base_version → 412 on
// drift) then resumes with the REAL outcome (H6) — applied_saved / applied_conflict.

const submitToolResult = vi.fn().mockResolvedValue('');
const applyEntityEdit = vi.fn();

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../providers', () => ({ useChatStream: () => ({ submitToolResult }) }));
vi.mock('@/features/glossary/api', () => ({
  glossaryApi: { applyEntityEdit: (...a: unknown[]) => applyEntityEdit(...a) },
}));

import { GlossaryDiffCard } from '../GlossaryDiffCard';
import type { ToolCallRecord } from '../../types';

function record(args: Record<string, unknown>): ToolCallRecord {
  return { tool: 'glossary_propose_entity_edit', ok: true, pending: true, runId: 'r1', toolCallId: 'c1', args };
}

describe('GlossaryDiffCard', () => {
  beforeEach(() => {
    submitToolResult.mockClear();
    applyEntityEdit.mockReset();
  });

  it('applies MULTIPLE changes in one atomic call and resumes applied_saved', async () => {
    applyEntityEdit.mockResolvedValue({});
    render(<GlossaryDiffCard record={record({
      book_id: 'b1', entity_id: 'e1', base_version: '2026-06-10T00:00:00Z',
      changes: [
        { target: 'attribute', attr_value_id: 'a1', field_label: 'Name', old_value: 'Nezha', new_value: 'Nezha III' },
        { target: 'short_description', field_label: 'Description', old_value: 'old', new_value: 'A fierce youth' },
      ],
    })} />);

    // both diff rows render
    expect(screen.getByText('Nezha III')).toBeInTheDocument();
    expect(screen.getByText('A fierce youth')).toBeInTheDocument();

    fireEvent.click(screen.getByText('glossaryEdit.apply'));

    await waitFor(() => expect(applyEntityEdit).toHaveBeenCalledTimes(1));
    // ONE atomic body carrying both the attribute + short_description, one base_version
    expect(applyEntityEdit).toHaveBeenCalledWith(
      'b1', 'e1',
      {
        base_version: '2026-06-10T00:00:00Z',
        short_description: 'A fierce youth',
        attributes: [{ attr_value_id: 'a1', original_value: 'Nezha III' }],
      },
      'tok',
    );
    await waitFor(() =>
      expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'applied_saved'),
    );
  });

  it('resumes applied_conflict when apply-edit returns 412', async () => {
    applyEntityEdit.mockRejectedValue(Object.assign(new Error('conflict'), { status: 412 }));
    render(<GlossaryDiffCard record={record({
      book_id: 'b1', entity_id: 'e1', base_version: 'v0',
      changes: [{ target: 'short_description', field_label: 'Description', old_value: 'old', new_value: 'new' }],
    })} />);

    fireEvent.click(screen.getByText('glossaryEdit.apply'));

    await waitFor(() =>
      expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'applied_conflict'),
    );
  });

  it('dismiss resumes dismissed without an apply-edit call', async () => {
    render(<GlossaryDiffCard record={record({
      book_id: 'b1', entity_id: 'e1', base_version: 'v0',
      changes: [{ target: 'short_description', field_label: 'Description', old_value: 'old', new_value: 'new' }],
    })} />);

    fireEvent.click(screen.getByText('glossaryEdit.dismiss'));

    await waitFor(() =>
      expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'dismissed'),
    );
    expect(applyEntityEdit).not.toHaveBeenCalled();
  });
});
