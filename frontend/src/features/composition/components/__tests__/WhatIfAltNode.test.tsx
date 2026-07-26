import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { WhatIfAltNode } from '../WhatIfAltNode';
import type { WhatIfAlt } from '../../hooks/useSceneWhatIf';
import type { Critic } from '../../types';

// WhatIfAltNode renders inside an <svg> (foreignObject) — wrap in one so jsdom is happy.
function renderNode(alt: WhatIfAlt, cb?: { onGenerate?: () => void; onView?: () => void; onRemove?: () => void }) {
  return render(
    <svg>
      <WhatIfAltNode
        alt={alt} pos={{ x: 0, y: 0 }}
        onRemove={cb?.onRemove ?? vi.fn()} onGenerate={cb?.onGenerate ?? vi.fn()} onView={cb?.onView ?? vi.fn()}
      />
    </svg>,
  );
}
const alt = (over: Partial<WhatIfAlt>): WhatIfAlt => ({ id: 'a1', title: 'Alternate 1', status: 'idle', ...over });
const judge: Critic = { coherence: 8, voice_match: 4, pacing: 6, canon_consistency: 9, violations: [] };

describe('WhatIfAltNode (WS-B3 M2 — lifecycle)', () => {
  it('idle → shows the Generate button (fires onGenerate)', () => {
    const onGenerate = vi.fn();
    renderNode(alt({ status: 'idle' }), { onGenerate });
    fireEvent.click(screen.getByTestId('whatif-alt-generate-a1'));
    expect(onGenerate).toHaveBeenCalled();
  });

  it('generating → shows a generating indicator, no Generate button', () => {
    renderNode(alt({ status: 'generating' }));
    expect(screen.getByTestId('whatif-alt-generating-a1')).toBeTruthy();
    expect(screen.queryByTestId('whatif-alt-generate-a1')).toBeNull();
  });

  it('ready + judge → shows the critic dims badge + View', () => {
    renderNode(alt({ status: 'ready', take: { ghost: 'an alternate', jobId: 'j1', judge } }));
    const badge = screen.getByTestId('whatif-alt-judge-a1');
    expect(badge.textContent).toContain('C8');
    expect(badge.textContent).toContain('V4');
    expect(badge.textContent).toContain('P6');
    expect(screen.getByTestId('whatif-alt-view-a1')).toBeTruthy();
  });

  it('ready but judge still pending → shows "judging…", no dims yet', () => {
    renderNode(alt({ status: 'ready', take: { ghost: 'g', jobId: 'j1', judge: null } }));
    expect(screen.getByTestId('whatif-alt-judge-a1').textContent).toContain('judging');
  });

  it('View fires onView; error → retry fires onGenerate', () => {
    const onView = vi.fn(); const onGenerate = vi.fn();
    renderNode(alt({ status: 'ready', take: { ghost: 'g', jobId: 'j', judge } }), { onView });
    fireEvent.click(screen.getByTestId('whatif-alt-view-a1'));
    expect(onView).toHaveBeenCalled();

    renderNode(alt({ id: 'a2', status: 'error' }), { onGenerate });
    fireEvent.click(screen.getByTestId('whatif-alt-retry-a2'));
    expect(onGenerate).toHaveBeenCalled();
  });
});
