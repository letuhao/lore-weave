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

// W1-residual — the History tab body is a separate controller component (it
// owns the fetch + provider deps). Stub it so the panel's tab-toggle is tested
// in isolation, without the auth/session providers.
vi.mock('../ContextHistoryTab', () => ({
  ContextHistoryTab: () => <div data-testid="context-history-tab" />,
}));

import {
  ContextBreakdownPanel,
  computeBreakdown,
  BREAKDOWN_CATEGORIES,
  CATEGORY_COLORS,
  CATEGORY_HEX,
} from '../ContextBreakdownPanel';
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

// W1-residual — the Now / History tab toggle.
describe('ContextBreakdownPanel tabs', () => {
  it('defaults to Now with the History body mounted-but-hidden', () => {
    render(<ContextBreakdownPanel budget={fullBudget} />);
    expect(screen.getByTestId('context-panel-tabs')).toBeInTheDocument();
    // Now body visible; the History body is kept mounted (state-preserving) but
    // CSS-hidden so a later toggle back doesn't remount + refetch from zero.
    expect(screen.getByTestId('context-now-body')).not.toHaveClass('hidden');
    expect(screen.getByTestId('context-history-body')).toHaveClass('hidden');
    // the live rows are present
    expect(screen.getByText('context_panel.cat.skills')).toBeInTheDocument();
  });

  it('switches to History and back to Now without unmounting either body', () => {
    render(<ContextBreakdownPanel budget={fullBudget} />);
    fireEvent.click(screen.getByTestId('context-tab-history'));
    // History body shown; Now body stays mounted but hidden (state-preserving).
    expect(screen.getByTestId('context-history-body')).not.toHaveClass('hidden');
    expect(screen.getByTestId('context-now-body')).toHaveClass('hidden');

    fireEvent.click(screen.getByTestId('context-tab-now'));
    // Both bodies remain mounted; only the hidden flag flips back.
    expect(screen.getByTestId('context-history-body')).toHaveClass('hidden');
    expect(screen.getByTestId('context-now-body')).not.toHaveClass('hidden');
  });
});

// M2 — CATEGORY_HEX is a hand-mirror of CATEGORY_COLORS (recharts `fill` needs a
// concrete hex, not a Tailwind class). TS enforces the KEY set matches but not
// the VALUES, so a recolor of one map without the other silently diverges (the
// chart segment vs the panel dot disagree). Pin both against the Tailwind *-400
// palette so a future one-sided recolor fails here.
describe('CATEGORY_COLORS ⇄ CATEGORY_HEX lockstep', () => {
  // Tailwind palette *-400 → hex (the shade both maps use).
  const TAILWIND_400_HEX: Record<string, string> = {
    'bg-amber-400': '#fbbf24',
    'bg-emerald-400': '#34d399',
    'bg-teal-400': '#2dd4bf',
    'bg-rose-400': '#fb7185',
    'bg-violet-400': '#a78bfa',
    'bg-fuchsia-400': '#e879f9',
    'bg-lime-400': '#a3e635',
    'bg-orange-400': '#fb923c',
    'bg-sky-400': '#38bdf8',
    'bg-cyan-400': '#22d3ee',
    'bg-indigo-400': '#818cf8',
    'bg-blue-400': '#60a5fa',
  };

  it('every category: CATEGORY_HEX equals its CATEGORY_COLORS Tailwind class hex', () => {
    for (const key of BREAKDOWN_CATEGORIES) {
      const cls = CATEGORY_COLORS[key];
      const expectedHex = TAILWIND_400_HEX[cls];
      // the class must be one we have a hex mapping for (guards a shade change)
      expect(expectedHex, `no hex mapping for ${key}'s class "${cls}"`).toBeDefined();
      expect(CATEGORY_HEX[key], `CATEGORY_HEX.${key} drifted from ${cls}`).toBe(expectedHex);
    }
  });

  it('both maps cover exactly the category vocabulary', () => {
    expect(Object.keys(CATEGORY_COLORS).sort()).toEqual([...BREAKDOWN_CATEGORIES].sort());
    expect(Object.keys(CATEGORY_HEX).sort()).toEqual([...BREAKDOWN_CATEGORIES].sort());
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
