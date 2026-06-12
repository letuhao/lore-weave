import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CanonGatePanel } from '../CanonGatePanel';
import type { CanonResult, CanonViolation } from '../../types';

const hardV: CanonViolation = {
  kind: 'gone_entity_present', source: 'llm_judge', entity_id: 'e1',
  name: 'Castor', status: 'gone', matched: 'Castor', confirmed: true, why: 'Castor died in chapter 3',
};
const advisoryV: CanonViolation = {
  kind: 'gone_entity_present', source: 'score_symbolic', entity_id: 'e2',
  name: 'Mira', status: 'gone', matched: 'Mira', confirmed: null,
};

function panel(canon: CanonResult, onRevise = vi.fn()) {
  render(<CanonGatePanel canon={canon} onRevise={onRevise} />);
  return onRevise;
}

describe('CanonGatePanel (A2-S4a — hard / advisory / unchecked)', () => {
  it('clean (checked, no violations) shows the clear line and nothing else', () => {
    panel({ violations: [], resolved: true, iterations: 0, status: 'checked' });
    expect(screen.getByTestId('canon-clear')).toBeTruthy();
    expect(screen.queryByTestId('canon-hard')).toBeNull();
    expect(screen.queryByTestId('canon-advisory')).toBeNull();
    expect(screen.queryByTestId('canon-unchecked')).toBeNull();
  });

  it('clean with iterations>0 surfaces the auto-revised badge', () => {
    panel({ violations: [], resolved: true, iterations: 2, status: 'checked' });
    expect(screen.getByText('canonAutoRevised')).toBeTruthy();
  });

  it('a HARD confirmed violation renders the red section + entity + why, with a Revise', () => {
    const onRevise = panel({ violations: [hardV], resolved: false, iterations: 1, status: 'checked' });
    expect(screen.getByTestId('canon-hard')).toBeTruthy();
    expect(screen.getByText('Castor')).toBeTruthy();
    expect(screen.getByText(/Castor died in chapter 3/)).toBeTruthy();
    expect(screen.queryByTestId('canon-clear')).toBeNull();
    fireEvent.click(screen.getByTestId('canon-revise-hard'));
    expect(onRevise).toHaveBeenCalledWith(hardV);
  });

  it('an ADVISORY (confirmed=null) violation renders the amber section, distinct from hard', () => {
    const onRevise = panel({ violations: [advisoryV], resolved: true, iterations: 0, status: 'checked' });
    expect(screen.getByTestId('canon-advisory')).toBeTruthy();
    expect(screen.queryByTestId('canon-hard')).toBeNull();
    expect(screen.getByText('Mira')).toBeTruthy();
    fireEvent.click(screen.getByTestId('canon-revise-advisory'));
    expect(onRevise).toHaveBeenCalledWith(advisoryV);
  });

  it('hard + advisory together render BOTH sections', () => {
    panel({ violations: [hardV, advisoryV], resolved: false, iterations: 2, status: 'checked' });
    expect(screen.getByTestId('canon-hard')).toBeTruthy();
    expect(screen.getByTestId('canon-advisory')).toBeTruthy();
  });

  it('checked but resolved=false with no surfaced hard row does NOT show a false-green clear line', () => {
    // /review-impl #1 — trust the authoritative `resolved`; never render green
    // "clear" when the backend says unresolved, even if no individual row surfaced.
    panel({ violations: [], resolved: false, iterations: 0, status: 'checked' });
    expect(screen.queryByTestId('canon-clear')).toBeNull();
  });

  it('a judge-CLEARED violation (confirmed=false) is defensively dropped → clear', () => {
    const cleared: CanonViolation = { ...hardV, confirmed: false };
    panel({ violations: [cleared], resolved: true, iterations: 1, status: 'checked' });
    expect(screen.queryByTestId('canon-hard')).toBeNull();
    expect(screen.queryByTestId('canon-advisory')).toBeNull();
    expect(screen.getByTestId('canon-clear')).toBeTruthy();
  });

  it.each([
    ['skipped_no_cast', 'canonUncheckedNoCast'],
    ['skipped_no_position', 'canonUncheckedNoPosition'],
    ['degraded', 'canonUncheckedDegraded'],
  ])('status %s warns "unchecked" (%s) and suppresses the clear line', (status, reasonKey) => {
    panel({ violations: [], resolved: true, iterations: 0, status });
    expect(screen.getByTestId('canon-unchecked')).toBeTruthy();
    expect(screen.getByText(new RegExp(reasonKey))).toBeTruthy();
    expect(screen.queryByTestId('canon-clear')).toBeNull();
  });
});
