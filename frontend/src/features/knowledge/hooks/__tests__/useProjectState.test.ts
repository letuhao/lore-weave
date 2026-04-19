import { describe, it, expect } from 'vitest';
import { deriveState, scopeOfJob } from '../useProjectState';
import type { ExtractionJobWire, GraphStatsResponse } from '../../api';
import type { Project } from '../../types';

function project(overrides: Partial<Project> = {}): Project {
  return {
    project_id: 'p1',
    user_id: 'u1',
    name: 'Test',
    description: '',
    project_type: 'translation',
    book_id: null,
    instructions: '',
    extraction_enabled: true,
    extraction_status: 'ready',
    embedding_model: 'bge-m3',
    embedding_dimension: 1024,
    extraction_config: {},
    last_extracted_at: null,
    estimated_cost_usd: '0',
    actual_cost_usd: '0',
    is_archived: false,
    version: 1,
    created_at: '2026-04-19T00:00:00Z',
    updated_at: '2026-04-19T00:00:00Z',
    ...overrides,
  };
}

function job(overrides: Partial<ExtractionJobWire> = {}): ExtractionJobWire {
  return {
    job_id: 'j1',
    user_id: 'u1',
    project_id: 'p1',
    status: 'running',
    scope: { kind: 'all' } as never,
    scope_range: null,
    llm_model: 'claude-sonnet-4-6',
    embedding_model: 'bge-m3',
    items_processed: 3,
    items_total: 10,
    cost_spent_usd: '0.50',
    max_spend_usd: '5.00',
    started_at: '2026-04-19T12:00:00Z',
    paused_at: null,
    completed_at: null,
    created_at: '2026-04-19T12:00:00Z',
    updated_at: '2026-04-19T12:00:00Z',
    current_cursor: null,
    error_message: null,
    // @ts-expect-error — BE ships scope as a bare string; wire overrides it below
    ...overrides,
  };
}

// The wire type's scope is BE's Literal ("chapters" | "chat" | …);
// deriveState handles the shape conversion internally. Tests pass bare
// strings to mirror the BE response.
function beJob(
  status: ExtractionJobWire['status'],
  overrides: Record<string, unknown> = {},
): ExtractionJobWire {
  return {
    ...job(),
    status,
    ...(overrides as Partial<ExtractionJobWire>),
    scope: (overrides.scope ?? 'all') as ExtractionJobWire['scope'],
  };
}

describe('deriveState', () => {
  it('returns "disabled" when extraction_enabled is false', () => {
    const s = deriveState(project({ extraction_enabled: false }), [], null);
    expect(s.kind).toBe('disabled');
  });

  it('returns "disabled" when extraction_enabled is true but no jobs', () => {
    const s = deriveState(project(), [], null);
    expect(s.kind).toBe('disabled');
  });

  it('returns "building_running" for job.status="running"', () => {
    const s = deriveState(project(), [beJob('running')], null);
    expect(s.kind).toBe('building_running');
    if (s.kind === 'building_running') {
      expect(s.job.job_id).toBe('j1');
      expect(s.job.items_processed).toBe(3);
    }
  });

  it('returns "building_running" for job.status="pending"', () => {
    const s = deriveState(project(), [beJob('pending')], null);
    expect(s.kind).toBe('building_running');
  });

  it('returns "building_paused_budget" when paused at spend cap', () => {
    const s = deriveState(
      project(),
      [beJob('paused', { cost_spent_usd: '5.00', max_spend_usd: '5.00' })],
      null,
    );
    expect(s.kind).toBe('building_paused_budget');
    if (s.kind === 'building_paused_budget') {
      expect(s.budgetRemaining).toBe(0);
    }
  });

  it('returns "building_paused_budget" when spent exceeds cap (safety)', () => {
    const s = deriveState(
      project(),
      [beJob('paused', { cost_spent_usd: '5.50', max_spend_usd: '5.00' })],
      null,
    );
    expect(s.kind).toBe('building_paused_budget');
    if (s.kind === 'building_paused_budget') {
      expect(s.budgetRemaining).toBe(0); // clamp to 0, not negative
    }
  });

  it('returns "building_paused_error" when paused with error_message', () => {
    const s = deriveState(
      project(),
      [beJob('paused', { cost_spent_usd: '0.50', error_message: 'rate limit' })],
      null,
    );
    expect(s.kind).toBe('building_paused_error');
    if (s.kind === 'building_paused_error') {
      expect(s.error).toBe('rate limit');
    }
  });

  it('returns "building_paused_user" when paused without budget-hit and no error', () => {
    const s = deriveState(
      project(),
      [beJob('paused', { cost_spent_usd: '1.00', max_spend_usd: '5.00' })],
      null,
    );
    expect(s.kind).toBe('building_paused_user');
  });

  it('returns "building_paused_user" when paused with no budget cap at all', () => {
    const s = deriveState(
      project(),
      [beJob('paused', { cost_spent_usd: '1.00', max_spend_usd: null })],
      null,
    );
    expect(s.kind).toBe('building_paused_user');
  });

  it('returns "complete" for job.status="complete" + uses stats when present', () => {
    const stats: GraphStatsResponse = {
      project_id: 'p1',
      entity_count: 100,
      fact_count: 200,
      event_count: 30,
      passage_count: 500,
      last_extracted_at: '2026-04-19T12:00:00Z',
    };
    const s = deriveState(project(), [beJob('complete')], stats);
    expect(s.kind).toBe('complete');
    if (s.kind === 'complete') {
      expect(s.stats.entity_count).toBe(100);
      expect(s.stats.last_extracted_at).toBe('2026-04-19T12:00:00Z');
    }
  });

  it('returns "complete" with empty stats when stats query not yet resolved', () => {
    const s = deriveState(project(), [beJob('complete')], null);
    expect(s.kind).toBe('complete');
    if (s.kind === 'complete') {
      expect(s.stats.entity_count).toBe(0);
      expect(s.stats.last_extracted_at).toBe('');
    }
  });

  it('returns "failed" for job.status="failed" with error message', () => {
    const s = deriveState(
      project(),
      [beJob('failed', { error_message: 'fatal: provider down' })],
      null,
    );
    expect(s.kind).toBe('failed');
    if (s.kind === 'failed') {
      expect(s.error).toBe('fatal: provider down');
      expect(s.canRetry).toBe(true);
    }
  });

  it('returns "failed" with fallback error when error_message is null', () => {
    const s = deriveState(project(), [beJob('failed', { error_message: null })], null);
    expect(s.kind).toBe('failed');
    if (s.kind === 'failed') {
      expect(s.error).toBe('unknown error');
    }
  });

  it('returns "disabled" for job.status="cancelled" (partial graph kept)', () => {
    const s = deriveState(project(), [beJob('cancelled')], null);
    expect(s.kind).toBe('disabled');
  });

  it('uses the NEWEST job (jobs[0]) — BE lists newest-first', () => {
    const s = deriveState(
      project(),
      [
        beJob('running', { job_id: 'new' }),
        beJob('complete', { job_id: 'old' }),
      ],
      null,
    );
    expect(s.kind).toBe('building_running');
  });
});

// review-impl F3 — scopeOfJob's chapter_range parser has special cases
// (valid range, missing field, wrong types, wrong length). Before this
// cycle those were only indirectly touched via deriveState — a BE
// contract drift on scope_range's shape would silently fall back to
// {kind:'chapters'} with no range and no test would catch it.
describe('scopeOfJob', () => {
  it('returns {kind:"all"} for scope="all"', () => {
    const s = scopeOfJob(beJob('running', { scope: 'all' }));
    expect(s).toEqual({ kind: 'all' });
  });

  it('returns {kind:"chat"} for scope="chat"', () => {
    const s = scopeOfJob(beJob('running', { scope: 'chat' }));
    expect(s).toEqual({ kind: 'chat' });
  });

  it('returns {kind:"glossary_sync"} for scope="glossary_sync"', () => {
    const s = scopeOfJob(beJob('running', { scope: 'glossary_sync' }));
    expect(s).toEqual({ kind: 'glossary_sync' });
  });

  it('returns {kind:"chapters"} without range when scope_range is null', () => {
    const s = scopeOfJob(beJob('running', { scope: 'chapters', scope_range: null }));
    expect(s).toEqual({ kind: 'chapters' });
  });

  it('returns {kind:"chapters", range} when scope_range.chapter_range is valid', () => {
    const s = scopeOfJob(
      beJob('running', {
        scope: 'chapters',
        scope_range: { chapter_range: [3, 15] },
      }),
    );
    expect(s).toEqual({
      kind: 'chapters',
      range: { from_sort: 3, to_sort: 15 },
    });
  });

  it('falls back to {kind:"chapters"} when chapter_range has wrong length', () => {
    const s = scopeOfJob(
      beJob('running', {
        scope: 'chapters',
        scope_range: { chapter_range: [3, 15, 99] },
      }),
    );
    expect(s).toEqual({ kind: 'chapters' });
  });

  it('falls back to {kind:"chapters"} when chapter_range contains a non-number', () => {
    const s = scopeOfJob(
      beJob('running', {
        scope: 'chapters',
        scope_range: { chapter_range: ['3', 15] },
      }),
    );
    expect(s).toEqual({ kind: 'chapters' });
  });

  it('falls back to {kind:"chapters"} when chapter_range is not an array', () => {
    const s = scopeOfJob(
      beJob('running', {
        scope: 'chapters',
        scope_range: { chapter_range: { from_sort: 3, to_sort: 15 } },
      }),
    );
    expect(s).toEqual({ kind: 'chapters' });
  });
});
