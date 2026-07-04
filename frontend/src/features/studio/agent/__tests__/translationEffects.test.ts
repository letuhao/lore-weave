// #16 Phase 4 (LIVE-SYNC audit, 2026-07-05) — Lane B effect handler for translation_job_control.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { clearEffectHandlers, runEffectHandlers, matchEffectHandlers, type EffectContext } from '../effectRegistry';
import type { StudioHost } from '../../host/StudioHostProvider';
import {
  translationJobControlEffect, registerTranslationEffectHandlers, _resetTranslationEffectHandlers,
} from '../handlers/translationEffects';

beforeEach(() => {
  clearEffectHandlers();
  _resetTranslationEffectHandlers();
});

const ctx = (over: Partial<EffectContext> = {}): EffectContext => ({
  tool: 'translation_job_control',
  result: { job_id: 'j1', status: 'cancelled' },
  bookId: 'b1',
  host: { publish: vi.fn() } as unknown as StudioHost,
  queryClient: { invalidateQueries: vi.fn() } as unknown as EffectContext['queryClient'],
  ...over,
});

describe('translationJobControlEffect (Lane B handler)', () => {
  it('invalidates the coverage matrix + segment-coverage + the chapter-panel refresh signal', () => {
    const c = ctx();
    translationJobControlEffect(c);
    const keys = (c.queryClient.invalidateQueries as ReturnType<typeof vi.fn>).mock.calls.map((call) => call[0].queryKey);
    expect(keys).toContainEqual(['translation-coverage', 'b1']);
    expect(keys).toContainEqual(['segment-coverage', 'b1']);
    expect(keys).toContainEqual(['translation', 'refresh', 'b1']);
  });
});

describe('registerTranslationEffectHandlers wiring', () => {
  it('routes cancel/pause (translation_job_control) through the registry', async () => {
    registerTranslationEffectHandlers();
    expect(matchEffectHandlers('translation_job_control')).toContain(translationJobControlEffect);
    await runEffectHandlers(ctx());
    // Idempotent registration — calling it again must not double-register.
    registerTranslationEffectHandlers();
    expect(matchEffectHandlers('translation_job_control')).toHaveLength(1);
  });

  it('does not match an unrelated translation tool (e.g. a read)', () => {
    registerTranslationEffectHandlers();
    expect(matchEffectHandlers('translation_job_status')).toHaveLength(0);
  });

  it('does not match resume/retry\'s confirm_action dispatch (out of scope — see file header)', () => {
    registerTranslationEffectHandlers();
    expect(matchEffectHandlers('confirm_action')).toHaveLength(0);
  });
});
