import { describe, it, expect, vi } from 'vitest';
import {
  classifyTranslationError,
  isRetryableTranslationError,
  withTimeout,
  TranslationTimeoutError,
} from '../translationError';

describe('classifyTranslationError', () => {
  it('maps 403 → forbidden, 404 → notfound, 5xx/network → retryable', () => {
    expect(classifyTranslationError(Object.assign(new Error(), { status: 403 })).kind).toBe('forbidden');
    expect(classifyTranslationError(Object.assign(new Error(), { status: 404 })).kind).toBe('notfound');
    expect(classifyTranslationError(Object.assign(new Error(), { status: 500 })).kind).toBe('retryable');
    expect(classifyTranslationError(new Error('network')).kind).toBe('retryable'); // no status
    expect(classifyTranslationError(undefined).kind).toBe('retryable');
  });

  it('only retryable errors are offered a Retry', () => {
    expect(isRetryableTranslationError(Object.assign(new Error(), { status: 500 }))).toBe(true);
    expect(isRetryableTranslationError(Object.assign(new Error(), { status: 403 }))).toBe(false);
  });
});

describe('withTimeout', () => {
  it('resolves when the promise settles before the deadline', async () => {
    await expect(withTimeout(Promise.resolve('ok'), 1000)).resolves.toBe('ok');
  });

  it('rejects with TranslationTimeoutError when the promise hangs past the deadline', async () => {
    vi.useFakeTimers();
    const hang = new Promise(() => {}); // never settles
    const raced = withTimeout(hang, 100);
    const assertion = expect(raced).rejects.toBeInstanceOf(TranslationTimeoutError);
    await vi.advanceTimersByTimeAsync(150);
    await assertion;
    vi.useRealTimers();
  });
});
