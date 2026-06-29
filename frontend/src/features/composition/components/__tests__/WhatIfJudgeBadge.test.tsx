import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { WhatIfJudgeBadge } from '../WhatIfJudgeBadge';
import type { Critic } from '../../types';

const mk = (c: number | null, v: number | null, p: number | null, k: number | null): Critic => ({
  coherence: c, voice_match: v, pacing: p, canon_consistency: k, violations: [],
});

describe('WhatIfJudgeBadge (M4 vs-canon delta)', () => {
  it('renders DELTA mode with ▲/▼/= when a canon baseline verdict exists', () => {
    render(<WhatIfJudgeBadge judge={mk(4, 3, 5, 2)} canon={mk(3, 3, 2, 4)} baselineAvailable judging={false} />);
    const badge = screen.getByTestId('whatif-judge-badge');
    expect(badge.getAttribute('data-mode')).toBe('delta');
    expect(badge.textContent).toContain('▲'); // coherence 4 vs 3
    expect(badge.textContent).toContain('▼'); // canon_consistency 2 vs 4
    expect(badge.textContent).toContain('='); // voice_match 3 vs 3
  });

  it('falls back to ABSOLUTE + "judging" note while the canon verdict loads', () => {
    render(<WhatIfJudgeBadge judge={mk(4, 3, 5, 2)} canon={null} baselineAvailable judging />);
    const badge = screen.getByTestId('whatif-judge-badge');
    expect(badge.getAttribute('data-mode')).toBe('absolute');
    expect(badge.textContent).toContain('C4'); // absolute take score
    expect(badge.textContent).toContain('whatif.vsCanon.judging');
  });

  it('shows "no canon baseline" when the anchor chapter has no draft', () => {
    render(<WhatIfJudgeBadge judge={mk(4, 3, 5, 2)} canon={null} baselineAvailable={false} judging={false} />);
    const badge = screen.getByTestId('whatif-judge-badge');
    expect(badge.getAttribute('data-mode')).toBe('absolute');
    expect(badge.textContent).toContain('whatif.vsCanon.noBaseline');
  });

  it('degrade: null take dims render as – in absolute mode (never fabricated)', () => {
    render(<WhatIfJudgeBadge judge={mk(null, null, null, null)} canon={null} baselineAvailable={false} judging={false} />);
    const badge = screen.getByTestId('whatif-judge-badge');
    expect(badge.textContent).toContain('C–');
  });
});
