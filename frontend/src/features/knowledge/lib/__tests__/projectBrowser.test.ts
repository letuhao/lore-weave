import { describe, it, expect } from 'vitest';
import { narrowProjects } from '../projectBrowser';
import type { Project } from '../../types';

// Minimal Project factory — only the fields narrowProjects reads.
function mk(over: Partial<Project>): Project {
  return {
    project_id: over.project_id ?? 'p',
    user_id: 'u',
    name: over.name ?? 'name',
    description: '',
    project_type: 'general',
    book_id: over.book_id ?? null,
    instructions: '',
    genre: null,
    extraction_enabled: true,
    tool_calling_enabled: true,
    memory_remember_confirm: false,
    extraction_status: over.extraction_status ?? 'disabled',
    embedding_model: null,
    embedding_dimension: null,
    rerank_model: null,
    rerank_model_source: 'none',
    extraction_config: {},
    last_extracted_at: null,
    estimated_cost_usd: '0',
    actual_cost_usd: '0',
    is_archived: over.is_archived ?? false,
    version: 1,
    created_at: over.created_at ?? '2026-01-01T00:00:00Z',
    updated_at: over.updated_at ?? '2026-01-01T00:00:00Z',
  } as Project;
}

const base = {
  search: '',
  sort: 'name_asc' as const,
  stateFilter: 'all' as const,
};

describe('narrowProjects', () => {
  it('filters by case-insensitive name substring', () => {
    const list = [
      mk({ project_id: 'a', name: 'Winds of the East' }),
      mk({ project_id: 'b', name: 'Northern Saga' }),
    ];
    const out = narrowProjects(list, { ...base, search: 'wind' });
    expect(out.map((p) => p.project_id)).toEqual(['a']);
  });

  it('matches a pasted book_id', () => {
    const list = [
      mk({ project_id: 'a', name: 'Alpha', book_id: 'BOOK-123' }),
      mk({ project_id: 'b', name: 'Beta', book_id: 'BOOK-999' }),
    ];
    const out = narrowProjects(list, { ...base, search: 'book-123' });
    expect(out.map((p) => p.project_id)).toEqual(['a']);
  });

  it('filters by extraction state, excluding archived from status buckets', () => {
    const list = [
      mk({ project_id: 'a', extraction_status: 'ready' }),
      mk({ project_id: 'b', extraction_status: 'failed' }),
      // archived + ready must NOT show under the "ready" bucket.
      mk({ project_id: 'c', extraction_status: 'ready', is_archived: true }),
    ];
    const out = narrowProjects(list, { ...base, stateFilter: 'ready' });
    expect(out.map((p) => p.project_id)).toEqual(['a']);
  });

  it('isolates archived rows under the archived filter', () => {
    const list = [
      mk({ project_id: 'a', is_archived: false }),
      mk({ project_id: 'b', is_archived: true }),
    ];
    const out = narrowProjects(list, { ...base, stateFilter: 'archived' });
    expect(out.map((p) => p.project_id)).toEqual(['b']);
  });

  it('sorts by name asc/desc', () => {
    const list = [mk({ name: 'Beta' }), mk({ name: 'Alpha' })];
    expect(
      narrowProjects(list, { ...base, sort: 'name_asc' }).map((p) => p.name),
    ).toEqual(['Alpha', 'Beta']);
    expect(
      narrowProjects(list, { ...base, sort: 'name_desc' }).map((p) => p.name),
    ).toEqual(['Beta', 'Alpha']);
  });

  it('sorts recent (newest updated first) and oldest', () => {
    const list = [
      mk({ project_id: 'old', updated_at: '2026-01-01T00:00:00Z' }),
      mk({ project_id: 'new', updated_at: '2026-06-01T00:00:00Z' }),
    ];
    expect(
      narrowProjects(list, { ...base, sort: 'recent' }).map((p) => p.project_id),
    ).toEqual(['new', 'old']);
    expect(
      narrowProjects(list, { ...base, sort: 'oldest' }).map((p) => p.project_id),
    ).toEqual(['old', 'new']);
  });

  it('does not mutate the input array', () => {
    const list = [mk({ name: 'Beta' }), mk({ name: 'Alpha' })];
    const snapshot = list.map((p) => p.name);
    narrowProjects(list, { ...base, sort: 'name_asc' });
    expect(list.map((p) => p.name)).toEqual(snapshot);
  });
});
