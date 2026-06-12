import { describe, it, expect } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useCampaignWizard } from '../useCampaignWizard';

const BOOK = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
const PROJ = '99999999-9999-9999-9999-999999999999';
const TR = '11111111-1111-1111-1111-111111111111';
const EX = '22222222-2222-2222-2222-222222222222';

describe('useCampaignWizard', () => {
  it('starts on the first step and gates advancement on required fields', () => {
    const { result } = renderHook(() => useCampaignWizard());
    expect(result.current.step).toBe('bookProject');
    // step 0 needs name + book + project
    expect(result.current.canAdvance(0)).toBe(false);
    act(() => {
      result.current.setField('name', 'My run');
      result.current.setField('bookId', BOOK);
      result.current.setField('projectId', PROJ);
    });
    expect(result.current.canAdvance(0)).toBe(true);
  });

  it('rejects an inverted chapter range but allows open ranges', () => {
    const { result } = renderHook(() => useCampaignWizard());
    expect(result.current.canAdvance(1)).toBe(true); // both null = whole book
    act(() => {
      result.current.setField('chapterFrom', 10);
      result.current.setField('chapterTo', 5);
    });
    expect(result.current.canAdvance(1)).toBe(false);
  });

  it('requires translator + extractor models to leave the Models step', () => {
    const { result } = renderHook(() => useCampaignWizard());
    expect(result.current.canAdvance(2)).toBe(false);
    act(() => result.current.setPick('translator', TR));
    expect(result.current.canAdvance(2)).toBe(false); // extractor still missing
    act(() => result.current.setPick('extractor', EX));
    expect(result.current.canAdvance(2)).toBe(true);
  });

  it('next/back clamp at the bounds', () => {
    const { result } = renderHook(() => useCampaignWizard());
    act(() => result.current.back()); // already at 0
    expect(result.current.stepIndex).toBe(0);
    act(() => { result.current.next(); result.current.next(); result.current.next(); result.current.next(); });
    expect(result.current.stepIndex).toBe(result.current.totalSteps - 1);
    expect(result.current.step).toBe('review');
  });

  it('buildCreatePayload maps each role to its campaign field (source=user_model when set)', () => {
    const { result } = renderHook(() => useCampaignWizard());
    act(() => {
      result.current.setField('name', '  My run  ');
      result.current.setField('bookId', BOOK);
      result.current.setField('projectId', PROJ);
      result.current.setField('budgetUsd', '12.50');
      result.current.setPick('translator', TR);
      result.current.setPick('extractor', EX);
    });
    const p = result.current.buildCreatePayload();
    expect(p.name).toBe('My run');               // trimmed
    expect(p.knowledge_project_id).toBe(PROJ);
    expect(p.translation_model_ref).toBe(TR);
    expect(p.translation_model_source).toBe('user_model');
    expect(p.knowledge_model_ref).toBe(EX);      // extractor → knowledge_model
    expect(p.budget_usd).toBe('12.50');
    expect(p.gating_mode).toBe('phase_barrier');  // D-S5C-GATING default
    // unset roles → null/null (not omitted)
    expect(p.verifier_model_ref).toBeNull();
    expect(p.verifier_model_source).toBeNull();
    expect(p.eval_judge_model_ref).toBeNull();
  });

  it('threads the estimate band into the create payload (G1); null when not estimated', () => {
    const { result } = renderHook(() => useCampaignWizard());
    expect(result.current.buildCreatePayload().est_usd_low).toBeNull();
    act(() => {
      result.current.setField('estUsdLow', '7.00');
      result.current.setField('estUsdHigh', '11.00');
    });
    const p = result.current.buildCreatePayload();
    expect(p.est_usd_low).toBe('7.00');
    expect(p.est_usd_high).toBe('11.00');
  });

  it('gating_mode is user-selectable (D-S5C-GATING)', () => {
    const { result } = renderHook(() => useCampaignWizard());
    act(() => {
      result.current.setField('name', 'r');
      result.current.setField('bookId', BOOK);
      result.current.setField('projectId', PROJ);
      result.current.setField('gatingMode', 'cold_start');
    });
    expect(result.current.buildCreatePayload().gating_mode).toBe('cold_start');
  });

  it('buildEstimateRequest includes ONLY the roles that were picked', () => {
    const { result } = renderHook(() => useCampaignWizard());
    act(() => {
      result.current.setField('bookId', BOOK);
      result.current.setPick('translator', TR);
    });
    const req = result.current.buildEstimateRequest();
    expect(Object.keys(req.models)).toEqual(['translator']);
    expect(req.models.translator).toEqual({ model_source: 'user_model', model_ref: TR });
    expect(req.book_id).toBe(BOOK);
  });
});
