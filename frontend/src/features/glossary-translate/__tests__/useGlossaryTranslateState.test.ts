import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useGlossaryTranslateState, isSameLanguageTarget } from '../useGlossaryTranslateState';

describe('useGlossaryTranslateState', () => {
  it('starts on config step with default target vi', () => {
    const { result } = renderHook(() => useGlossaryTranslateState());
    expect(result.current.state.step).toBe('config');
    expect(result.current.state.targetLanguage).toBe('vi');
    expect(result.current.canClose).toBe(true);
  });

  it('advances through config to confirm', () => {
    const { result } = renderHook(() => useGlossaryTranslateState());
    act(() => {
      result.current.setModelRef('model-1');
      result.current.goNext();
    });
    expect(result.current.state.step).toBe('confirm');
  });

  it('jumps to progress when job is created', () => {
    const { result } = renderHook(() => useGlossaryTranslateState());
    act(() => {
      result.current.setJobCreated('job-1', 3, {
        estimated_input_tokens: 100,
        estimated_output_tokens: 50,
        estimated_total_tokens: 150,
        llm_calls: 3,
        entity_count: 3,
        attr_count: 6,
      });
      result.current.goToStep('progress');
    });
    expect(result.current.state.step).toBe('progress');
    expect(result.current.state.jobId).toBe('job-1');
    expect(result.current.canClose).toBe(false);
  });

  it('reset() returns to initial config step', () => {
    const { result } = renderHook(() => useGlossaryTranslateState());
    act(() => {
      result.current.setJobCreated('job-1', 1, {
        estimated_input_tokens: 1,
        estimated_output_tokens: 1,
        estimated_total_tokens: 2,
        llm_calls: 1,
        entity_count: 1,
        attr_count: 1,
      });
      result.current.goToStep('progress');
      result.current.reset();
    });
    expect(result.current.state.step).toBe('config');
    expect(result.current.state.jobId).toBeNull();
  });
});

describe('isSameLanguageTarget', () => {
  it('returns false when source undefined', () => {
    expect(isSameLanguageTarget(undefined, 'vi')).toBe(false);
  });

  it('returns true when codes match', () => {
    expect(isSameLanguageTarget('zh', 'zh')).toBe(true);
  });
});
