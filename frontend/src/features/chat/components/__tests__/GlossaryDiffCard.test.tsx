import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// Glossary-assistant P3 — the edit-existing diff card: Apply issues a
// version-checked PATCH (If-Match: base_version) and resumes the run with the
// REAL outcome (H6) — applied_saved on 200, applied_conflict on 412.

const submitToolResult = vi.fn().mockResolvedValue('');
const patchEntity = vi.fn();
const patchAttributeValue = vi.fn();

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../providers', () => ({ useChatStream: () => ({ submitToolResult }) }));
vi.mock('@/features/glossary/api', () => ({
  glossaryApi: {
    patchEntity: (...a: unknown[]) => patchEntity(...a),
    patchAttributeValue: (...a: unknown[]) => patchAttributeValue(...a),
  },
}));

import { GlossaryDiffCard } from '../GlossaryDiffCard';
import type { ToolCallRecord } from '../../types';

function record(args: Record<string, unknown>): ToolCallRecord {
  return { tool: 'glossary_propose_entity_edit', ok: true, pending: true, runId: 'r1', toolCallId: 'c1', args };
}

describe('GlossaryDiffCard', () => {
  beforeEach(() => {
    submitToolResult.mockClear();
    patchEntity.mockReset();
    patchAttributeValue.mockReset();
  });

  it('applies an attribute edit with If-Match and resumes applied_saved', async () => {
    patchAttributeValue.mockResolvedValue({});
    render(<GlossaryDiffCard record={record({
      book_id: 'b1', entity_id: 'e1', attr_value_id: 'a1', base_version: '2026-06-10T00:00:00Z',
      target: 'attribute', field_label: 'Name', old_value: 'Nezha', new_value: 'Nezha III',
    })} />);

    fireEvent.click(screen.getByText('glossaryEdit.apply'));

    await waitFor(() => expect(patchAttributeValue).toHaveBeenCalled());
    expect(patchAttributeValue).toHaveBeenCalledWith(
      'b1', 'e1', 'a1', { original_value: 'Nezha III' }, 'tok', { ifMatch: '2026-06-10T00:00:00Z' },
    );
    await waitFor(() =>
      expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'applied_saved'),
    );
  });

  it('resumes applied_conflict when the PATCH returns 412', async () => {
    patchEntity.mockRejectedValue(Object.assign(new Error('conflict'), { status: 412 }));
    render(<GlossaryDiffCard record={record({
      book_id: 'b1', entity_id: 'e1', base_version: 'v0',
      target: 'short_description', field_label: 'Description', old_value: 'old', new_value: 'new',
    })} />);

    fireEvent.click(screen.getByText('glossaryEdit.apply'));

    await waitFor(() =>
      expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'applied_conflict'),
    );
    expect(patchEntity).toHaveBeenCalledWith(
      'b1', 'e1', { short_description: 'new' }, 'tok', { ifMatch: 'v0' },
    );
  });

  it('dismiss resumes dismissed without any PATCH', async () => {
    render(<GlossaryDiffCard record={record({
      book_id: 'b1', entity_id: 'e1', base_version: 'v0',
      target: 'short_description', field_label: 'Description', old_value: 'old', new_value: 'new',
    })} />);

    fireEvent.click(screen.getByText('glossaryEdit.dismiss'));

    await waitFor(() =>
      expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'dismissed'),
    );
    expect(patchEntity).not.toHaveBeenCalled();
    expect(patchAttributeValue).not.toHaveBeenCalled();
  });
});
