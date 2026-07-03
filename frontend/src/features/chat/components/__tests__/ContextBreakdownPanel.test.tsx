import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

// Chat Quality Wave W2 — the context drill-down panel. Two suites:
//   1. computeBreakdown — the pure math (percentages, zero-collapse, free
//      space, the compact-threshold fraction).
//   2. render — rows, the zero one-liner, the memory-section expand, the
//      manage action gating, the footer lines.

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

import { ContextBreakdownPanel, computeBreakdown } from '../ContextBreakdownPanel';
import type { ContextBudget } from '../../types';

const fullBudget: ContextBudget = {
  used_tokens: 3676,
  context_length: 8192,
  effective_limit: 8000,
  pct: 0.4595,
  until_compact_pct: 0.2905,
  baseline_tokens: 3667,
  breakdown: {
    system_prompt: 0,
    memory_knowledge: { total: 50, sections: { instructions: 33, glossary_entities: 17 } },
    working_memory: 0,
    steering: 0,
    skills: 1907,
    plan_nudge: 0,
    book_note: 0,
    attached_context: 0,
    history: 9,
    tool_results: 0,
    frontend_tool_schemas: 1484,
    mcp_tool_schemas: 193,
  },
};

describe('computeBreakdown', () => {
  it('splits non-zero rows (vocabulary order) from zero categories', () => {
    const c = computeBreakdown(fullBudget);
    expect(c.rows.map((r) => r.key)).toEqual([
      'memory_knowledge', 'skills', 'history', 'frontend_tool_schemas', 'mcp_tool_schemas',
    ]);
    expect(c.zeros).toEqual([
      'system_prompt', 'working_memory', 'steering', 'plan_nudge', 'book_note',
      'attached_context', 'tool_results',
    ]);
  });

  it('computes % of used per row', () => {
    const c = computeBreakdown(fullBudget);
    const skills = c.rows.find((r) => r.key === 'skills')!;
    expect(skills.tokens).toBe(1907);
    expect(skills.pctOfUsed).toBeCloseTo((1907 / 3676) * 100, 5);
    const memory = c.rows.find((r) => r.key === 'memory_knowledge')!;
    expect(memory.tokens).toBe(50); // nested {total, sections} → total
    expect(memory.sections).toEqual({ instructions: 33, glossary_entities: 17 });
  });

  it('free space = limit − used; compact threshold = pct + until_compact_pct', () => {
    const c = computeBreakdown(fullBudget);
    expect(c.limitTokens).toBe(8000);
    expect(c.freeTokens).toBe(8000 - 3676);
    expect(c.compactAtFraction).toBeCloseTo(0.75, 5);
  });

  it('unknown limit → null free space + null compact fraction', () => {
    const c = computeBreakdown({
      used_tokens: 100, context_length: null, effective_limit: null, pct: null,
      breakdown: { history: 100 },
    });
    expect(c.limitTokens).toBeNull();
    expect(c.freeTokens).toBeNull();
    expect(c.compactAtFraction).toBeNull();
    expect(c.rows).toEqual([{ key: 'history', tokens: 100, pctOfUsed: 100 }]);
  });

  it('no breakdown at all → every category is zero', () => {
    const c = computeBreakdown({ used_tokens: 10, context_length: 100, effective_limit: 90, pct: 0.11 });
    expect(c.rows).toEqual([]);
    expect(c.zeros).toHaveLength(12);
  });
});

describe('ContextBreakdownPanel', () => {
  it('renders the non-zero rows + the zero one-liner + footer lines', () => {
    render(<ContextBreakdownPanel budget={fullBudget} />);
    expect(screen.getByTestId('context-breakdown-panel')).toBeInTheDocument();
    expect(screen.getByText('context_panel.cat.skills')).toBeInTheDocument();
    expect(screen.getByText('context_panel.cat.history')).toBeInTheDocument();
    // zero categories collapse into one line, not rows
    expect(screen.getByTestId('context-zero-line').textContent).toContain('context_panel.cat.steering');
    expect(screen.getByTestId('context-baseline-line')).toBeInTheDocument();
    expect(screen.getByTestId('context-free-line')).toBeInTheDocument();
    expect(screen.getByTestId('context-until-compact-line')).toBeInTheDocument();
    expect(screen.getByTestId('context-compact-marker')).toBeInTheDocument();
  });

  it('expands the memory sections on toggle', () => {
    render(<ContextBreakdownPanel budget={fullBudget} />);
    expect(screen.queryByTestId('context-memory-sections')).toBeNull();
    fireEvent.click(screen.getByTestId('context-row-memory-toggle'));
    const sections = screen.getByTestId('context-memory-sections');
    expect(sections.textContent).toContain('instructions');
    expect(sections.textContent).toContain('glossary_entities');
  });

  it('shows the manage action on tool/skill rows only when wired', () => {
    const onManage = vi.fn();
    const { rerender } = render(<ContextBreakdownPanel budget={fullBudget} onManageTools={onManage} />);
    fireEvent.click(screen.getByTestId('context-manage-skills'));
    expect(onManage).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('context-manage-mcp_tool_schemas')).toBeInTheDocument();
    // not wired → hidden (embedded surfaces without the rack)
    rerender(<ContextBreakdownPanel budget={fullBudget} />);
    expect(screen.queryByTestId('context-manage-skills')).toBeNull();
  });

  it('renders without breakdown data (header-only budget)', () => {
    render(<ContextBreakdownPanel budget={{ used_tokens: 10, context_length: 100, effective_limit: 90, pct: 0.11 }} />);
    expect(screen.getByTestId('context-breakdown-panel')).toBeInTheDocument();
    expect(screen.getByTestId('context-zero-line')).toBeInTheDocument();
  });
});

// W3 — the "Compact now" footer section (steerable persisted compact).
describe('ContextBreakdownPanel compact section', () => {
  const controls = (overrides: Partial<{ pending: boolean; compactedBeforeSeq: number | null }> = {}) => ({
    pending: false,
    compactedBeforeSeq: null as number | null,
    onCompact: vi.fn(),
    onClearCompact: vi.fn(),
    ...overrides,
  });

  it('is hidden when no controls are wired (embedded/archived surfaces)', () => {
    render(<ContextBreakdownPanel budget={fullBudget} />);
    expect(screen.queryByTestId('context-compact-section')).toBeNull();
  });

  it('calls onCompact with the typed preservation instructions', () => {
    const c = controls();
    render(<ContextBreakdownPanel budget={fullBudget} compact={c} />);
    fireEvent.change(screen.getByTestId('context-compact-instructions'), {
      target: { value: 'keep all plot promises' },
    });
    fireEvent.click(screen.getByTestId('context-compact-now'));
    expect(c.onCompact).toHaveBeenCalledTimes(1);
    expect(c.onCompact).toHaveBeenCalledWith('keep all plot promises');
  });

  it('calls onCompact with empty instructions when none typed', () => {
    const c = controls();
    render(<ContextBreakdownPanel budget={fullBudget} compact={c} />);
    fireEvent.click(screen.getByTestId('context-compact-now'));
    expect(c.onCompact).toHaveBeenCalledTimes(1);
    expect(c.onCompact).toHaveBeenCalledWith('');
  });

  it('disables the button + input while pending', () => {
    const c = controls({ pending: true });
    render(<ContextBreakdownPanel budget={fullBudget} compact={c} />);
    const button = screen.getByTestId('context-compact-now');
    expect(button).toBeDisabled();
    expect(screen.getByTestId('context-compact-instructions')).toBeDisabled();
    expect(button.textContent).toContain('context_panel.compact.pending');
    fireEvent.click(button);
    expect(c.onCompact).not.toHaveBeenCalled();
  });

  it('shows the compacted-through marker only when the session was compacted', () => {
    const { rerender } = render(<ContextBreakdownPanel budget={fullBudget} compact={controls()} />);
    expect(screen.queryByTestId('context-compacted-through')).toBeNull();
    rerender(<ContextBreakdownPanel budget={fullBudget} compact={controls({ compactedBeforeSeq: 9 })} />);
    expect(screen.getByTestId('context-compacted-through')).toBeInTheDocument();
  });

  it('clear-compact button: visible only with a compact marker; calls onClearCompact', () => {
    const c = controls({ compactedBeforeSeq: 9 });
    const { rerender } = render(<ContextBreakdownPanel budget={fullBudget} compact={controls()} />);
    expect(screen.queryByTestId('context-compact-clear')).toBeNull();
    rerender(<ContextBreakdownPanel budget={fullBudget} compact={c} />);
    const btn = screen.getByTestId('context-compact-clear');
    expect(btn.textContent).toContain('context_panel.compact.clear');
    fireEvent.click(btn);
    expect(c.onClearCompact).toHaveBeenCalledTimes(1);
  });

  it('clear-compact button is disabled while pending', () => {
    const c = controls({ compactedBeforeSeq: 9, pending: true });
    render(<ContextBreakdownPanel budget={fullBudget} compact={c} />);
    const btn = screen.getByTestId('context-compact-clear');
    expect(btn).toBeDisabled();
    fireEvent.click(btn);
    expect(c.onClearCompact).not.toHaveBeenCalled();
  });
});
