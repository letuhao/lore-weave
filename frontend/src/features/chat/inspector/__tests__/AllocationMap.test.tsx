import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import type { ContextTraceFrame } from '../../types';
import { AllocationMap } from '../AllocationMap';

// Verify-by-EFFECT for the §11 allocation map. Reuses computeBreakdown; here we
// prove the rendered bar + legend reflect the per-category tokens (width ∝ tokens,
// a legend row each, the tooltip carries label+tokens+%, and the empty state is
// honest when nothing was recorded).

const frame = (breakdown: ContextTraceFrame['breakdown']): ContextTraceFrame => ({
  used_tokens: 3528,
  context_length: 131072,
  effective_limit: 128000,
  pct: 0.02,
  target: 32000,
  breakdown,
});

const BD = {
  skills: 1500,
  history: 500,
  frontend_tool_schemas: 1000,
  memory_knowledge: { total: 500, sections: {} },
};

describe('AllocationMap', () => {
  it('allocation total = sum of non-zero category tokens (kfmt header)', () => {
    render(<AllocationMap frame={frame(BD)} />);
    // 1500 + 500 + 1000 + 500 = 3500 → "3.5K"
    expect(screen.getByTestId('inspector-allocation').textContent).toContain('3.5K');
  });

  it('segmented bar: one segment per non-zero category, width ∝ tokens', () => {
    render(<AllocationMap frame={frame(BD)} />);
    const segs = screen.getByTestId('inspector-allocation').querySelectorAll('[data-alloc-seg]');
    const byKey = Object.fromEntries(
      Array.from(segs).map((s) => [s.getAttribute('data-alloc-seg'), (s as HTMLElement).style.width]),
    );
    // skills is 1500/3500 ≈ 42.857%, history 500/3500 ≈ 14.28% — width proportional
    expect(byKey.skills).toContain('42.85');
    expect(byKey.history).toContain('14.28');
  });

  it('hover tooltip carries category label + tokens + % (the §11a-required triple)', () => {
    render(<AllocationMap frame={frame(BD)} />);
    const skills = screen
      .getByTestId('inspector-allocation')
      .querySelector('[data-alloc-seg="skills"]');
    expect(skills?.getAttribute('title')).toBe('skills · 1,500 tok · 43%');
  });

  it('legend renders a row per non-zero category with its token count', () => {
    render(<AllocationMap frame={frame(BD)} />);
    const alloc = screen.getByTestId('inspector-allocation');
    // frontend_tool_schemas → humanized label + its token count in the legend
    expect(within(alloc).getByText('frontend tool schemas')).toBeInTheDocument();
    expect(within(alloc).getByText('1,000')).toBeInTheDocument();
  });

  it('renders the NEW Context Budget Law categories (summary / chapter / reasoning)', () => {
    // §11a extends context_breakdown with summary/chapter/reasoning — the map must
    // render them as segments + legend rows once a tier populates them (not silently drop).
    render(<AllocationMap frame={frame({ summary: 400, chapter: 300, reasoning: 200 })} />);
    const alloc = screen.getByTestId('inspector-allocation');
    for (const key of ['summary', 'chapter', 'reasoning']) {
      expect(alloc.querySelector(`[data-alloc-seg="${key}"]`)).toBeInTheDocument();
    }
    // and the humanized legend labels appear
    expect(within(alloc).getByText('summary')).toBeInTheDocument();
    expect(within(alloc).getByText('reasoning')).toBeInTheDocument();
  });

  it('empty state is honest when no category tokens were recorded', () => {
    render(<AllocationMap frame={frame({})} />);
    expect(screen.getByText(/no per-category allocation recorded/i)).toBeInTheDocument();
  });
});
