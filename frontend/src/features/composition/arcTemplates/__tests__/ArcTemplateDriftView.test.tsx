// Wave-4 (D-ARC-TEMPLATE-DRIFT-VIEW) — the structured drift view over the real ArcConformance
// shape. Covers the edge cases from the spec §4.5: derived summary vs the all-zero clean verdict,
// empty threads, pacing not-comparable, null motif_code, folded placements.
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ArcConformance } from '../../motif/types';
import { ArcTemplateDriftView } from '../ArcTemplateDriftView';

const t = ((k: string, o?: Record<string, unknown>) => {
  // A minimal i18n stub that interpolates {{var}} from options — enough to assert derived copy.
  let s = (o?.defaultValue as string) ?? k;
  if (o) for (const [key, val] of Object.entries(o)) s = s.replace(new RegExp(`{{${key}}}`, 'g'), String(val));
  return s;
}) as never;

function report(over: Partial<ArcConformance> = {}): ArcConformance {
  return {
    scope: 'arc', available: true, coarse: true, causal_verified: false,
    arc_template_id: 'a1', arc_name: 'Arc', chapter_count: 2,
    thread_progress: [{ thread: 't1', label: 'Revenge', planned: 2, covered: 2, missing: [] }],
    pacing: { comparable: true, planned: [10, 90], realized: [{ chapter_index: 1, avg_tension: 11, scenes: 1 }], max_drift: 0 },
    succession: { causal_verified: false, threads: [{ thread: 't1', label: 'Revenge', transitions: 1, legal: 1, unrelated: 0, violations: [] }] },
    unmaterialized: [],
    ...over,
  };
}

describe('ArcTemplateDriftView', () => {
  it('shows the CLEAN verdict when every signal is zero (no drift)', () => {
    render(<ArcTemplateDriftView report={report()} t={t} />);
    expect(screen.getByTestId('arc-drift-clean')).toBeInTheDocument();
    expect(screen.queryByTestId('arc-drift-summary')).not.toBeInTheDocument();
  });

  it('derives a drift summary from coverage gaps + violations + folded placements', () => {
    render(<ArcTemplateDriftView report={report({
      thread_progress: [{ thread: 't1', label: 'Revenge', planned: 3, covered: 1, missing: [{ motif_code: 'a', ord: 1 }, { motif_code: 'b', ord: 2 }] }],
      succession: { causal_verified: false, threads: [{ thread: 't1', label: 'Revenge', transitions: 2, legal: 1, unrelated: 0, violations: [{ from_motif_id: 'x', to_motif_id: 'y' }] }] },
      unmaterialized: [{ motif_code: 'c', thread: 't1', ord: 3 }],
    })} t={t} />);
    const s = screen.getByTestId('arc-drift-summary').textContent!;
    expect(s).toMatch(/2 coverage gap/);
    expect(s).toMatch(/1 ordering issue/);
    expect(s).toMatch(/1 folded/);
    expect(screen.getByTestId('arc-drift-violation-t1')).toBeInTheDocument();
    expect(screen.getByTestId('arc-drift-folded')).toBeInTheDocument();
  });

  it('a pacing-ONLY drift (no structural gaps) reads as pacing drift, never "0·0·0"', () => {
    render(<ArcTemplateDriftView report={report({
      // structure clean (covered==planned, no violations, nothing folded) but the curve moved
      pacing: { comparable: true, planned: [10, 90], realized: [{ chapter_index: 1, avg_tension: 40, scenes: 1 }], max_drift: 7 },
    })} t={t} />);
    expect(screen.queryByTestId('arc-drift-clean')).not.toBeInTheDocument();
    const s = screen.getByTestId('arc-drift-summary').textContent!;
    expect(s).toMatch(/pacing drifted/);
    expect(s).not.toMatch(/0 coverage/);
  });

  it('renders a null motif_code by its ord, never crashing or printing "null"', () => {
    render(<ArcTemplateDriftView report={report({
      thread_progress: [{ thread: 't1', label: 'Revenge', planned: 2, covered: 1, missing: [{ motif_code: null, ord: 4 }] }],
    })} t={t} />);
    const cell = screen.getByTestId('arc-drift-missing-t1').textContent!;
    expect(cell).toContain('#4');
    expect(cell).not.toContain('null');
  });

  it('suppresses pacing drift + shows the honest note when not comparable', () => {
    render(<ArcTemplateDriftView report={report({
      pacing: { comparable: false, planned: [], realized: [], max_drift: null },
    })} t={t} />);
    expect(screen.queryByTestId('arc-drift-max')).not.toBeInTheDocument();
    expect(screen.getByTestId('arc-drift-pacing').textContent).toMatch(/Not comparable/);
  });

  it('renders an honest empty when the template has no threads', () => {
    render(<ArcTemplateDriftView report={report({ thread_progress: [] })} t={t} />);
    expect(screen.getByText(/no threads to compare/i)).toBeInTheDocument();
  });
});
