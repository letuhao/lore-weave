import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// MCP fan-out (C-PROPOSE) — the GENERIC record-diff card: renders N old→new rows
// from changes[] and Apply issues the domain's version-checked PATCH
// (If-Match base_version → 409/412 on drift), then resumes with the REAL outcome.

const submitToolResult = vi.fn().mockResolvedValue('');
const applyRecordEdit = vi.fn();

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../providers', () => ({ useChatStream: () => ({ submitToolResult }) }));
vi.mock('../../actionsApi', () => ({
  actionsApi: { applyRecordEdit: (...a: unknown[]) => applyRecordEdit(...a) },
}));

import { RecordDiffCard } from '../RecordDiffCard';
import type { ToolCallRecord } from '../../types';

function record(args: Record<string, unknown>): ToolCallRecord {
  return { tool: 'propose_record_edit', ok: true, pending: true, runId: 'r1', toolCallId: 'c1', args };
}

describe('RecordDiffCard', () => {
  beforeEach(() => {
    submitToolResult.mockClear();
    applyRecordEdit.mockReset();
  });

  it('applies the changes via the domain PATCH and resumes applied_saved', async () => {
    applyRecordEdit.mockResolvedValue({});
    render(<RecordDiffCard record={record({
      domain: 'book',
      resource_ref: { book_id: 'b1', chapter_id: 'ch1' },
      base_version: 'v7',
      changes: [{ field_label: 'Title', old_value: 'Old', new_value: 'New title' }],
    })} />);

    expect(screen.getByText('New title')).toBeInTheDocument();
    fireEvent.click(screen.getByText('recordEdit.apply'));

    await waitFor(() => expect(applyRecordEdit).toHaveBeenCalledWith(
      'book',
      { book_id: 'b1', chapter_id: 'ch1' },
      'v7',
      [{ field_label: 'Title', old_value: 'Old', new_value: 'New title' }],
      'tok',
    ));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'applied_saved'));
  });

  it('resumes applied_conflict on a 412', async () => {
    applyRecordEdit.mockRejectedValue(Object.assign(new Error('conflict'), { status: 412 }));
    render(<RecordDiffCard record={record({
      domain: 'book', resource_ref: { book_id: 'b1' }, base_version: 'v0',
      changes: [{ field_label: 'Title', old_value: 'a', new_value: 'b' }],
    })} />);
    fireEvent.click(screen.getByText('recordEdit.apply'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'applied_conflict'));
  });

  it('dismiss resumes dismissed without a PATCH', async () => {
    render(<RecordDiffCard record={record({
      domain: 'book', resource_ref: { book_id: 'b1' }, base_version: 'v0',
      changes: [{ field_label: 'Title', old_value: 'a', new_value: 'b' }],
    })} />);
    fireEvent.click(screen.getByText('recordEdit.dismiss'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'dismissed'));
    expect(applyRecordEdit).not.toHaveBeenCalled();
  });

  it('a malformed proposal resolves applied_error (never inert)', async () => {
    render(<RecordDiffCard record={record({ domain: 'book', changes: [] })} />);
    fireEvent.click(screen.getByText('recordEdit.apply'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'applied_error'));
    expect(applyRecordEdit).not.toHaveBeenCalled();
  });
});
