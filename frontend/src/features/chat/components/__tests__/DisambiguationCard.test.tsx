import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// DQ-T76 — the pick-one card.
//
// 🔴 WHY THE AUTHOR AND NOT THE AGENT, measured on the corpus:
//   - the supplier is ALREADY named to the model in the refusal (argument_emitters covers
//     632 of 723 failures), and of 605 (session, tool) pairs that failed this way only 51
//     (8%) ever succeeded with that tool again in the same session;
//   - fetching automatically resolves ~6% — 76% of suppliers return MANY rows, and when the
//     author says "delete the map" and there are twelve, no fetch says which.
// So the server fetches the rows and a person chooses.

const submitToolResult = vi.fn().mockResolvedValue('');

vi.mock('../../providers', () => ({ useChatStream: () => ({ submitToolResult }) }));

import { DisambiguationCard, isDisambiguationRecord } from '../DisambiguationCard';
import type { ToolCallRecord } from '../../types';

const A = 'e6c27ac3-08e2-5a6d-a08a-7941a4d6b90f';
const B = '11111111-2222-4333-8444-555555555555';

function record(overrides: Record<string, unknown> = {}): ToolCallRecord {
  return {
    tool: 'world_map_delete',
    ok: true,
    pending: true,
    runId: 'r1',
    toolCallId: 'c1',
    args: {
      kind: 'disambiguation',
      tool: 'world_map_delete',
      param: 'map_id',
      supplier: 'world_map_list',
      candidates: [{ id: A, name: 'Emberfall Reach' }, { id: B, name: 'The Sundered Coast' }],
      truncated: false,
      total: 2,
      ...overrides,
    },
  } as unknown as ToolCallRecord;
}

describe('DisambiguationCard', () => {
  beforeEach(() => submitToolResult.mockClear());

  it('routes by the args.kind marker, never by tool name', () => {
    // The record's `tool` is the SERVER tool that needs the id, so name-routing is impossible.
    expect(isDisambiguationRecord(record())).toBe(true);
    expect(isDisambiguationRecord({ ...record(), pending: false } as ToolCallRecord)).toBe(false);
    expect(isDisambiguationRecord(
      { tool: 'world_map_delete', pending: true, args: { kind: 'tool_approval' } } as unknown as ToolCallRecord,
    )).toBe(false);
  });

  it('shows each candidate by NAME — the id is what the tool needs, not what a person reads', () => {
    render(<DisambiguationCard record={record()} />);
    expect(screen.getAllByTestId('disambiguation-option')).toHaveLength(2);
    expect(screen.getAllByTestId('disambiguation-name').map((n) => n.textContent))
      .toEqual(['Emberfall Reach', 'The Sundered Coast']);
  });

  it('sends the chosen id in applied_text with a CLOSED-SET outcome', async () => {
    // 🔴 The id must NOT ride the outcome enum. FrontendToolOutcome is a closed union;
    // widening it to carry a UUID turns every exhaustive check into a string comparison.
    render(<DisambiguationCard record={record()} />);
    fireEvent.click(screen.getAllByTestId('disambiguation-option')[1]);
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledTimes(1));
    expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'disambiguated', B);
  });

  it('"None of these" cancels rather than picking one on the author\'s behalf', async () => {
    render(<DisambiguationCard record={record()} />);
    fireEvent.click(screen.getByTestId('disambiguation-cancel'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledTimes(1));
    expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'cancelled');
  });

  it('accepts exactly one choice — a double click cannot resume the run twice', async () => {
    render(<DisambiguationCard record={record()} />);
    const opts = screen.getAllByTestId('disambiguation-option');
    fireEvent.click(opts[0]);
    fireEvent.click(opts[1]);
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledTimes(1));
    expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'disambiguated', A);
  });

  it('an unnamed row is still offered — hiding it would remove a valid choice', () => {
    render(<DisambiguationCard record={record({ candidates: [{ id: A }] })} />);
    expect(screen.getAllByTestId('disambiguation-option')).toHaveLength(1);
    // Asserted by TEST ID, not by the rendered label: t() returns the KEY under test i18n,
    // so a text assertion here would be testing the harness rather than the card.
    expect(screen.getByTestId('disambiguation-unnamed')).toBeInTheDocument();
  });

  it('says when the list is truncated instead of showing a prefix as if it were all', () => {
    render(<DisambiguationCard record={record({ truncated: true, total: 44 })} />);
    expect(screen.getByTestId('disambiguation-truncated')).toHaveAttribute('data-total', '44');
  });
});
