import { describe, it, expect } from 'vitest';
import { readBackendError } from '../readBackendError';

function errWithBody(body: unknown): Error {
  return Object.assign(new Error('statusText fallback'), { body });
}

describe('readBackendError (shared AI-task error reader)', () => {
  it('prefers a string detail', () => {
    expect(readBackendError(errWithBody({ detail: 'entity locked' }))).toBe('entity locked');
  });

  it('reads detail.message (FastAPI HTTPException(detail={message}))', () => {
    expect(readBackendError(errWithBody({ detail: { message: 'empty response' } }))).toBe('empty response');
  });

  it('falls back to top-level body.message', () => {
    expect(readBackendError(errWithBody({ message: 'bad gateway reason' }))).toBe('bad gateway reason');
  });

  it('falls back to err.message when body carries nothing usable', () => {
    expect(readBackendError(errWithBody({ detail: {} }))).toBe('statusText fallback');
  });

  it('stringifies a non-Error', () => {
    expect(readBackendError('boom')).toBe('boom');
  });
});
