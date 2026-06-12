import { describe, it, expect } from 'vitest';
import { classifyJobError } from '../types';

// Direct unit coverage of the pure classifier (LE-PROD slice A, /review-impl #3).
// JobsPanel.test exercises it indirectly for 3 cases; this pins EVERY branch so the
// defensive enum-repr arm isn't dead-untested and the alt-phrasings don't drift.
describe('classifyJobError', () => {
  it('returns the empty/null sentinel for blank input', () => {
    for (const v of [null, undefined, '', '   ']) {
      expect(classifyJobError(v)).toEqual({ key: null, raw: '' });
    }
  });

  it('maps both gate-lock phrasings to the gateLocked key, preserving raw', () => {
    const a = "refused: technique 'fabrication' gate-locked (eval not cleared)";
    const b = 'the enrichment eval gate has not cleared (run the eval first)';
    expect(classifyJobError(a)).toEqual({ key: 'jobs.error.gateLocked', raw: a });
    expect(classifyJobError(b)).toEqual({ key: 'jobs.error.gateLocked', raw: b });
  });

  it('maps a TypeName-prefixed exception repr to internal', () => {
    const raw = "KeyError: <EntityKind.CHARACTER: 'character'>";
    expect(classifyJobError(raw)).toEqual({ key: 'jobs.error.internal', raw });
  });

  it('maps a bare enum repr (no Type: prefix) to internal via the defensive arm', () => {
    const raw = "<EntityKind.CHARACTER: 'character'>";
    expect(classifyJobError(raw)).toEqual({ key: 'jobs.error.internal', raw });
  });

  it('maps a Traceback dump to internal', () => {
    const raw = 'Traceback (most recent call last): File "x.py", line 1';
    expect(classifyJobError(raw)).toEqual({ key: 'jobs.error.internal', raw });
  });

  it('maps the slice-B insufficient_grounding note to actionable copy', () => {
    const raw = 'insufficient_grounding: 2 gap(s) had no usable corpus grounding — paste reference context or use fabrication';
    expect(classifyJobError(raw)).toEqual({
      key: 'jobs.error.insufficientGrounding',
      raw,
    });
  });

  it('shows an already-human message verbatim (key=null)', () => {
    for (const raw of [
      'no gaps to enrich (all targets fully described)',
      "unknown technique 'foo'",
      'paused: cost_cap before 玉虛宮',
    ]) {
      expect(classifyJobError(raw)).toEqual({ key: null, raw });
    }
  });

  it('trims surrounding whitespace before classifying', () => {
    expect(classifyJobError('  KeyError: boom  ')).toEqual({
      key: 'jobs.error.internal',
      raw: 'KeyError: boom',
    });
  });
});
