import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// EDIT-ATOMIC — the edit-existing diff card: renders N old→new rows from
// `changes[]` and Apply issues ONE atomic apply-edit (base_version → 412 on
// drift) then resumes with the REAL outcome (H6) — applied_saved / applied_conflict.

const submitToolResult = vi.fn().mockResolvedValue('');
const applyEntityEdit = vi.fn();
// Mutable so a test can mount the card on a surface that knows its own book.
const stream = vi.hoisted(() => ({ ambientBookId: null as string | null }));

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../providers', () => ({
  useChatStream: () => ({ submitToolResult, ambientBookId: stream.ambientBookId }),
}));
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
    stream.ambientBookId = null;
  });

  it('writes to the book the AUTHOR is on, not the one the model named', async () => {
    // REGRESSION LOCK. `book_id` arrives as a model-supplied tool argument, and a model that
    // fills it wrong redirects the write. Observed live: an ENTITY id landed in the `book_id`
    // slot, so Apply POSTed to `/books/<entity-id>/…` and 403'd. That was loud only by luck —
    // the same slip naming a book the caller DOES own would write to the wrong book in silence.
    stream.ambientBookId = 'the-open-book';
    applyEntityEdit.mockResolvedValue({});
    render(<GlossaryDiffCard record={record({
      book_id: 'e1',            // the model put the entity id here
      entity_id: 'e1', base_version: 'v0',
      changes: [{ target: 'short_description', field_label: 'Description', old_value: 'o', new_value: 'n' }],
    })} />);

    fireEvent.click(screen.getByText('glossaryEdit.apply'));

    await waitFor(() => expect(applyEntityEdit).toHaveBeenCalledTimes(1));
    expect(applyEntityEdit.mock.calls[0][0]).toBe('the-open-book');
  });

  it('falls back to the argument on a surface with no book of its own', async () => {
    // The global chat page carries no book context; the argument is all there is.
    stream.ambientBookId = null;
    applyEntityEdit.mockResolvedValue({});
    render(<GlossaryDiffCard record={record({
      book_id: 'b-from-args', entity_id: 'e1', base_version: 'v0',
      changes: [{ target: 'short_description', field_label: 'Description', old_value: 'o', new_value: 'n' }],
    })} />);

    fireEvent.click(screen.getByText('glossaryEdit.apply'));

    await waitFor(() => expect(applyEntityEdit).toHaveBeenCalledTimes(1));
    expect(applyEntityEdit.mock.calls[0][0]).toBe('b-from-args');
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
