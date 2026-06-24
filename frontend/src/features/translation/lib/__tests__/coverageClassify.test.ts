import { describe, it, expect } from 'vitest';
import type { BookCoverageResponse, CoverageCell } from '../../api';
import {
  classifyCell,
  classifyChapters,
  coverageMapFor,
  needsIds,
} from '../coverageClassify';

const cell = (over: Partial<CoverageCell>): CoverageCell => ({
  has_active: false,
  active_version_num: null,
  latest_version_num: null,
  latest_status: null,
  version_count: 0,
  ...over,
});

describe('classifyCell', () => {
  it('absent cell → untranslated', () => {
    expect(classifyCell(undefined)).toBe('untranslated');
  });
  it('fresh active → translated', () => {
    expect(classifyCell(cell({ has_active: true, latest_status: 'completed', is_glossary_stale: false }))).toBe(
      'translated',
    );
  });
  it('active but glossary stale → stale', () => {
    expect(classifyCell(cell({ has_active: true, latest_status: 'completed', is_glossary_stale: true }))).toBe('stale');
  });
  it('running attempt → running (even with no active yet)', () => {
    expect(classifyCell(cell({ has_active: false, latest_status: 'running' }))).toBe('running');
  });
  it('running takes precedence over a stale active', () => {
    expect(classifyCell(cell({ has_active: true, is_glossary_stale: true, latest_status: 'running' }))).toBe('running');
  });
  it('no active + failed latest → failed', () => {
    expect(classifyCell(cell({ has_active: false, latest_status: 'failed' }))).toBe('failed');
  });
  it('fresh active wins even when a newer attempt failed', () => {
    // active completed + a later failed re-translate: gate still skips it, so not "failed".
    expect(classifyCell(cell({ has_active: true, is_glossary_stale: false, latest_status: 'failed' }))).toBe(
      'translated',
    );
  });
  it('pending (queued, no active yet) → running (in-flight, not re-submittable)', () => {
    // Gate only skips completed rows; a re-submit of a pending chapter would dupe.
    expect(classifyCell(cell({ has_active: false, latest_status: 'pending' }))).toBe('running');
  });
});

describe('coverageMapFor + classifyChapters + needsIds', () => {
  const coverage: BookCoverageResponse = {
    book_id: 'b1',
    known_languages: ['vi'],
    coverage: [
      { chapter_id: 'c1', languages: { vi: cell({ has_active: true, is_glossary_stale: false }) } }, // translated
      { chapter_id: 'c2', languages: { vi: cell({ has_active: true, is_glossary_stale: true }) } }, // stale
      { chapter_id: 'c3', languages: { vi: cell({ has_active: false, latest_status: 'failed' }) } }, // failed
      // c4 absent from coverage → untranslated
      { chapter_id: 'c5', languages: { en: cell({ has_active: true }) } }, // only EN → vi untranslated
    ],
  };

  it('scenario: 2000 done + new chapters → only the needy are targeted', () => {
    const ids = ['c1', 'c2', 'c3', 'c4', 'c5'];
    const cells = coverageMapFor(coverage, 'vi');
    const { byId, counts } = classifyChapters(ids, cells);
    expect(counts).toEqual({ total: 5, untranslated: 2, translated: 1, stale: 1, failed: 1, running: 0 });
    expect(needsIds(byId).sort()).toEqual(['c2', 'c3', 'c4', 'c5']);
  });

  it('in-flight (pending/running) chapters stay out of the needs-set', () => {
    const cov: BookCoverageResponse = {
      book_id: 'b1',
      known_languages: ['vi'],
      coverage: [
        { chapter_id: 'p', languages: { vi: cell({ has_active: false, latest_status: 'pending' }) } },
        { chapter_id: 'r', languages: { vi: cell({ has_active: false, latest_status: 'running' }) } },
        { chapter_id: 'u', languages: {} }, // untranslated
      ],
    };
    const { byId, counts } = classifyChapters(['p', 'r', 'u'], coverageMapFor(cov, 'vi'));
    expect(counts.running).toBe(2);
    expect(needsIds(byId)).toEqual(['u']);
  });

  it('empty lang → empty map → everything untranslated', () => {
    const cells = coverageMapFor(coverage, '');
    expect(cells.size).toBe(0);
    const { counts } = classifyChapters(['c1', 'c2'], cells);
    expect(counts.untranslated).toBe(2);
  });
});
