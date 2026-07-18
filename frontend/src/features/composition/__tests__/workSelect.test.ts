import { describe, expect, it } from 'vitest';
import { resolveActiveWork, selectCanonicalWork, selectDerivatives } from '../workSelect';
import type { Work, WorkResolution } from '../types';

// Minimal Work fixtures — only the fields workSelect reads.
const work = (project_id: string, source_work_id?: string | null): Work =>
  ({ project_id, source_work_id } as unknown as Work);

const candidatesResolution = (candidates: Work[]): WorkResolution =>
  ({ status: 'candidates', work: null, candidates, book_project_id: null, book_project_ids: [] });

describe('selectCanonicalWork', () => {
  it('returns the Work with no source even when a derivative is sorted FIRST (not index 0)', () => {
    const canon = work('canon');
    const deriv = work('deriv', 'canon');
    // derivative first — candidates[0] would have been WRONG
    expect(selectCanonicalWork([deriv, canon])?.project_id).toBe('canon');
  });

  it('resolves a Work whose source_work_id is UNDEFINED (the `=== null` trap)', () => {
    const canon = work('canon'); // source_work_id absent (undefined), like most fixtures
    expect(selectCanonicalWork([canon])?.project_id).toBe('canon');
  });

  it('returns null when every candidate is a derivative', () => {
    expect(selectCanonicalWork([work('d1', 'c'), work('d2', 'c')])).toBeNull();
  });
});

describe('selectDerivatives', () => {
  it('returns only the Works that branch from a source', () => {
    const out = selectDerivatives([work('canon'), work('d1', 'canon'), work('d2', 'canon')]);
    expect(out.map((w) => w.project_id)).toEqual(['d1', 'd2']);
  });
});

describe('resolveActiveWork', () => {
  it('short-circuits on a `found` resolution', () => {
    const w = work('canon');
    const res: WorkResolution = { status: 'found', work: w, candidates: [], book_project_id: null, book_project_ids: [] };
    expect(resolveActiveWork(res, 'anything')?.project_id).toBe('canon');
  });

  it('returns the ACTIVE candidate when the pref matches one', () => {
    const res = candidatesResolution([work('canon'), work('deriv', 'canon')]);
    expect(resolveActiveWork(res, 'deriv')?.project_id).toBe('deriv');
  });

  it('falls back to canonical when the pref is unset', () => {
    const res = candidatesResolution([work('deriv', 'canon'), work('canon')]);
    expect(resolveActiveWork(res, undefined)?.project_id).toBe('canon');
  });

  it('falls back to canonical when the pref is stale/foreign (no matching candidate)', () => {
    const res = candidatesResolution([work('canon'), work('deriv', 'canon')]);
    expect(resolveActiveWork(res, 'archived-or-foreign')?.project_id).toBe('canon');
  });

  it('returns null for non-work statuses (none/unavailable) and undefined resolution', () => {
    expect(resolveActiveWork(undefined, undefined)).toBeNull();
    const none: WorkResolution = { status: 'none', work: null, candidates: [], book_project_id: null, book_project_ids: [] };
    expect(resolveActiveWork(none, 'x')).toBeNull();
  });
});
