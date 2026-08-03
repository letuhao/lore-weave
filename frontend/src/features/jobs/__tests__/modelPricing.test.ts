import { describe, expect, it } from 'vitest';

import type { UserModel } from '@/features/ai-models/api';
import { estimateTotalJobCost, estimateTokenCost, findJobModelPricing } from '../modelPricing';

const model = {
  user_model_id: 'm1',
  provider_credential_id: 'p1',
  provider_kind: 'openai',
  provider_model_name: 'qwen3',
  alias: 'Qwen',
  pricing: { input_per_mtok: 2.5, output_per_mtok: 10 },
} as UserModel;

describe('job model pricing', () => {
  it('estimates input and output tokens at current per-million rates', () => {
    expect(estimateTokenCost(1_000_000, 500_000, model.pricing)).toBe(7.5);
  });

  it('prefers the stable model ref and falls back to the resolved name', () => {
    expect(findJobModelPricing({ model: 'other', params: { model_ref: 'm1' } }, [model])).toEqual(model.pricing);
    expect(findJobModelPricing({ model: 'QWEN', params: null }, [model])).toEqual(model.pricing);
  });

  it('extrapolates total cost from current spend and progress', () => {
    expect(estimateTotalJobCost(0.22, { done: 55, total: 216 })).toBeCloseTo(0.864, 6);
    expect(estimateTotalJobCost(0.22, { done: 216, total: 216 })).toBeCloseTo(0.22, 6);
    expect(estimateTotalJobCost(0.22, { done: 0, total: 216 })).toBeNull();
  });

  it('returns no hint when pricing or token counts are unavailable', () => {
    expect(estimateTokenCost(100, 20, undefined)).toBeNull();
    expect(estimateTokenCost(null, null, model.pricing)).toBeNull();
  });
});
