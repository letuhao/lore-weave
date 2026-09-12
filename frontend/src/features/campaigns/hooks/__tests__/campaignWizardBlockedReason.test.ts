// T23 — the campaign wizard must say WHY it will not advance.
//
// `canAdvance` returned a bare boolean, so Next disabled itself silently and a user missing one of
// four preconditions was left to guess which. The campaign engine has more ways to be blocked than
// most — a knowledge project is required, chapters must be KG-indexed and in range, MANAGE grant is
// needed, and both model roles must be picked — and a missing one otherwise surfaces as a 400 from
// the server after the whole form has been filled in.
//
// Same defect T2 fixed on "Continue from cursor", and fixed the same way, deliberately.
import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { act } from 'react';

import { useCampaignWizard } from '../useCampaignWizard';

function wizard() {
  return renderHook(() => useCampaignWizard());
}

describe('useCampaignWizard — blockedReason (T23)', () => {
  it('names the MISSING NAME on the first step', () => {
    const { result } = wizard();
    expect(result.current.blockedReason(0)).toMatch(/name/i);
  });

  it('names the missing knowledge project specifically', () => {
    const { result } = wizard();
    act(() => {
      result.current.setField('name', 'Batch run');
      result.current.setField('bookId', 'b1');
    });
    expect(result.current.blockedReason(0)).toMatch(/knowledge project/i);
  });

  it('returns null once the step is satisfiable, so nothing renders (NV-7)', () => {
    const { result } = wizard();
    act(() => {
      result.current.setField('name', 'Batch run');
      result.current.setField('bookId', 'b1');
      result.current.setField('projectId', 'p1');
    });
    expect(result.current.blockedReason(0)).toBeNull();
    expect(result.current.canAdvance(0)).toBe(true);
  });

  it('distinguishes WHICH model role is missing, not just that one is', () => {
    const { result } = wizard();
    expect(result.current.blockedReason(2)).toMatch(/extractor and a translator/i);
    act(() => result.current.setPick('extractor', 'm1'));
    expect(result.current.blockedReason(2)).toMatch(/translator/i);
    expect(result.current.blockedReason(2)).not.toMatch(/extractor and/i);
  });

  it('agrees with canAdvance — a reason without a block, or a block without a reason, is a bug', () => {
    const { result } = wizard();
    for (const step of [0, 1, 2, 3]) {
      expect(result.current.blockedReason(step) === null).toBe(result.current.canAdvance(step));
    }
  });
});
