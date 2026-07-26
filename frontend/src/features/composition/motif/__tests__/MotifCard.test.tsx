// W6 §7.1 — MotifCard 4 variants + color co-encoding (asserted by TEXT presence,
// not color) + the system-card-has-no-edit-affordance rule.
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MotifCard } from '../components/MotifCard';
import type { Motif } from '../types';

const ME = 'user-1';

function makeMotif(over: Partial<Motif> = {}): Motif {
  return {
    id: 'm1', owner_user_id: ME, code: 'c', language: 'en', visibility: 'private',
    kind: 'sequence', category: null, name: 'My Motif', summary: 'a summary', genre_tags: ['xianxia'],
    roles: [], beats: [], preconditions: [], effects: [], tension_target: 3, emotion_target: null,
    info_asymmetry: null, examples: [{ text: 'a concrete example' }], abstraction_confidence: null,
    source: 'authored', source_version: null, judge_score: null, mining_support: null,
    status: 'active', version: 1, ...over,
  };
}

const noop = vi.fn();

describe('MotifCard variants + co-encoding', () => {
  it('own active motif → "active" variant, Open present, no Adopt', () => {
    render(<MotifCard motif={makeMotif()} meUserId={ME} onOpen={noop} onAdopt={noop} />);
    const card = screen.getByTestId('motif-card-m1');
    expect(card).toHaveAttribute('data-variant', 'active');
    expect(screen.getByTestId('motif-card-open-m1')).toBeInTheDocument();
    expect(screen.queryByTestId('motif-card-adopt-m1')).toBeNull();
  });

  it('system motif → tier word "System" present (co-encoded, not color-only); adoptable', () => {
    render(<MotifCard motif={makeMotif({ owner_user_id: null, visibility: 'unlisted' })} meUserId={ME} onOpen={noop} onAdopt={noop} />);
    // tier chip carries the WORD (the i18n key for system) — co-encoding §5.3
    expect(screen.getByTestId('motif-card-tier-m1').textContent).toContain('motif.tier.system');
    expect(screen.getByTestId('motif-card-m1')).toHaveAttribute('data-variant', 'adoptable');
    expect(screen.getByTestId('motif-card-adopt-m1')).toBeInTheDocument();
  });

  it("another user's public motif → adoptable variant + Adopt action", () => {
    render(<MotifCard motif={makeMotif({ owner_user_id: 'user-2', visibility: 'public' })} meUserId={ME} onOpen={noop} onAdopt={noop} />);
    expect(screen.getByTestId('motif-card-m1')).toHaveAttribute('data-variant', 'adoptable');
    expect(screen.getByTestId('motif-card-adopt-m1')).toBeInTheDocument();
  });

  it('mined draft → dashed "draft" variant', () => {
    render(<MotifCard motif={makeMotif({ status: 'draft', source: 'mined' })} meUserId={ME} onOpen={noop} />);
    expect(screen.getByTestId('motif-card-m1')).toHaveAttribute('data-variant', 'draft');
  });

  it('tension renders the NUMBER (T3) — not hue alone', () => {
    render(<MotifCard motif={makeMotif({ tension_target: 3 })} meUserId={ME} onOpen={noop} />);
    expect(screen.getByTestId('motif-card-tension-m1').textContent).toContain('T3');
  });

  it('S-08: an archived motif with onRestore shows a Restore action that fires restore', () => {
    const onRestore = vi.fn();
    render(<MotifCard motif={makeMotif({ status: 'archived' })} meUserId={ME} onOpen={noop} onRestore={onRestore} />);
    const btn = screen.getByTestId('motif-card-restore-m1');
    btn.click();
    expect(onRestore).toHaveBeenCalledWith('m1');
  });

  it('S-08: Restore is NOT shown on a non-archived row, nor when onRestore is absent', () => {
    render(<MotifCard motif={makeMotif({ status: 'active' })} meUserId={ME} onOpen={noop} onRestore={vi.fn()} />);
    expect(screen.queryByTestId('motif-card-restore-m1')).toBeNull();        // active row → no restore
    render(<MotifCard motif={makeMotif({ status: 'archived' })} meUserId={ME} onOpen={noop} />);
    expect(screen.queryByTestId('motif-card-restore-m1')).toBeNull();        // no handler → no restore
  });
});
