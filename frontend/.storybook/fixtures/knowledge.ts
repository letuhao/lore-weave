// C13 — shared fixtures for Storybook knowledge-dialog stories.
//
// Each factory takes a partial override and returns a fresh object.
// Fresh clones matter because stories that mutate (e.g. `fn()` spies)
// should not leak state between renders inside the same preview
// session. The `overrides` param is the deep-spread pattern from
// ProjectStateCard.stories.tsx scaled up to dialog state.
//
// Types mirror production shapes — no test-only `Partial<T>` tricks.
// If BE changes the wire format, tsc catches the fixture first.
//
// Fixture IDs use the all-zero UUID family so they're clearly
// synthetic in DevTools / network panels.

import type {
  Project,
  BenchmarkStatus,
  BenchmarkRunResponse,
} from '../../src/features/knowledge/types';
import type {
  CostEstimate,
  ExtractionJobSummary,
} from '../../src/features/knowledge/types/projectState';
import type {
  ExtractionJobWire,
  ChangeEmbeddingModelNoop,
  ChangeEmbeddingModelResult,
  UserCostSummary,
} from '../../src/features/knowledge/api';
import type { UserModel } from '../../src/features/ai-models/api';

// Base project: book-typed, extraction ready, bge-m3 embedding. Used as
// the default parent for BuildGraph / ChangeModel dialogs.
export function projectFixture(overrides: Partial<Project> = {}): Project {
  return {
    project_id: '00000000-0000-0000-0000-000000000001',
    user_id: '00000000-0000-0000-0000-0000000000aa',
    name: 'Storybook Test Project',
    description: 'Synthetic project for Storybook preview',
    project_type: 'book',
    book_id: '00000000-0000-0000-0000-000000000b01',
    instructions: '',
    extraction_enabled: true,
    extraction_status: 'ready',
    embedding_model: 'bge-m3',
    embedding_dimension: 1024,
    extraction_config: {},
    last_extracted_at: '2026-04-20T08:00:00Z',
    estimated_cost_usd: '0.00',
    actual_cost_usd: '1.23',
    is_archived: false,
    version: 3,
    created_at: '2026-04-01T00:00:00Z',
    updated_at: '2026-04-20T08:00:00Z',
    ...overrides,
  };
}

// No-book variant — defaults BuildGraphDialog to scope='all'.
export function projectFixtureNoBook(overrides: Partial<Project> = {}): Project {
  return projectFixture({
    project_type: 'general',
    book_id: null,
    name: 'General Notes Project',
    ...overrides,
  });
}

// ── Benchmark variants ─────────────────────────────────────────────────

export function benchmarkStatusPassed(
  overrides: Partial<BenchmarkStatus> = {},
): BenchmarkStatus {
  return {
    has_run: true,
    passed: true,
    run_id: '00000000-0000-0000-0000-00000000bcd1',
    embedding_model: 'bge-m3',
    recall_at_3: 0.87,
    mrr: 0.74,
    created_at: '2026-04-18T10:30:00Z',
    ...overrides,
  };
}

export function benchmarkStatusFailed(
  overrides: Partial<BenchmarkStatus> = {},
): BenchmarkStatus {
  return {
    has_run: true,
    passed: false,
    run_id: '00000000-0000-0000-0000-00000000bcd2',
    embedding_model: 'bge-m3',
    recall_at_3: 0.42,
    mrr: 0.31,
    created_at: '2026-04-18T10:30:00Z',
    ...overrides,
  };
}

export function benchmarkStatusNoRun(
  overrides: Partial<BenchmarkStatus> = {},
): BenchmarkStatus {
  return {
    has_run: false,
    passed: null,
    run_id: null,
    embedding_model: null,
    recall_at_3: null,
    mrr: null,
    created_at: null,
    ...overrides,
  };
}

// POST /benchmark-run response — returned synchronously after ~15-60s.
export function benchmarkRunFixture(
  overrides: Partial<BenchmarkRunResponse> = {},
): BenchmarkRunResponse {
  return {
    run_id: '00000000-0000-0000-0000-00000000bcd3',
    embedding_model: 'bge-m3',
    passed: true,
    recall_at_3: 0.89,
    mrr: 0.76,
    avg_score_positive: 0.82,
    negative_control_max_score: 0.48,
    stddev_recall: 0.03,
    stddev_mrr: 0.04,
    runs: 3,
    ...overrides,
  };
}

// ── Cost / estimate fixtures ───────────────────────────────────────────

export function costEstimateFixture(
  overrides: Partial<CostEstimate> = {},
): CostEstimate {
  return {
    items_total: 52,
    items: { chapters: 50, chat_turns: 0, glossary_entities: 2 },
    estimated_tokens: 125_000,
    estimated_cost_usd_low: '0.42',
    estimated_cost_usd_high: '0.71',
    estimated_duration_seconds: 180,
    ...overrides,
  };
}

export function userCostsFixture(
  overrides: Partial<UserCostSummary> = {},
): UserCostSummary {
  return {
    all_time_usd: '12.34',
    current_month_usd: '2.10',
    monthly_budget_usd: '25.00',
    monthly_remaining_usd: '22.90',
    ...overrides,
  };
}

// ── Extraction job fixtures ────────────────────────────────────────────

// ExtractionJobWire — returned by POST /extraction/start. Stories that
// need the "Confirming → completed" visual should use this for the
// startHandler response.
export function extractionJobWireFixture(
  overrides: Partial<ExtractionJobWire> = {},
): ExtractionJobWire {
  return {
    job_id: '00000000-0000-0000-0000-0000000000a1',
    user_id: '00000000-0000-0000-0000-0000000000aa',
    project_id: '00000000-0000-0000-0000-000000000001',
    scope: 'all',
    scope_range: null,
    status: 'running',
    llm_model: 'claude-haiku-4-5-20251001',
    embedding_model: 'bge-m3',
    max_spend_usd: '5.00',
    items_processed: 0,
    items_total: 52,
    cost_spent_usd: '0.00',
    current_cursor: null,
    started_at: '2026-04-24T12:00:00Z',
    paused_at: null,
    completed_at: null,
    created_at: '2026-04-24T12:00:00Z',
    updated_at: '2026-04-24T12:00:00Z',
    error_message: null,
    project_name: null,
    current_chapter_title: null,
    ...overrides,
  };
}

// ExtractionJobSummary — UI-derived shape used by ErrorViewerDialog.
export function jobSummaryFixture(
  overrides: Partial<ExtractionJobSummary> = {},
): ExtractionJobSummary {
  return {
    job_id: '00000000-0000-0000-0000-0000000000b1',
    status: 'failed',
    scope: { kind: 'all' },
    items_processed: 23,
    items_total: 52,
    cost_spent_usd: '0.87',
    max_spend_usd: '5.00',
    started_at: '2026-04-24T10:15:00Z',
    error_message: 'Provider returned 429 — rate limit exceeded',
    ...overrides,
  };
}

// ── Change-model response variants ─────────────────────────────────────

export function changeModelNoOpFixture(
  overrides: Partial<ChangeEmbeddingModelNoop> = {},
): ChangeEmbeddingModelNoop {
  return {
    message: 'model unchanged',
    current_model: 'bge-m3',
    ...overrides,
  };
}

export function changeModelResultFixture(
  overrides: Partial<ChangeEmbeddingModelResult> = {},
): ChangeEmbeddingModelResult {
  return {
    project_id: '00000000-0000-0000-0000-000000000001',
    previous_model: 'bge-m3',
    new_model: 'text-embedding-3-small',
    nodes_deleted: 152,
    extraction_status: 'disabled',
    ...overrides,
  };
}

// ── User-models fixtures ───────────────────────────────────────────────
//
// Two flavours because BuildGraphDialog asks for chat-capable (its LLM
// dropdown) while EmbeddingModelPicker asks for embedding-capable (its
// own dropdown). Same `/v1/model-registry/user-models` endpoint — BE
// filters by `capability` query param. Our MSW handler doesn't
// introspect the query, so stories that render dialogs containing the
// picker should use `userModelsFixtureEmbedding()` and accept that the
// LLM dropdown would (in a real BE call) return a different list.
// For mixed-need stories, use `userModelsFixtureAll()` which merges
// both — realistic enough for preview.

export function userModelsFixtureChat(): { items: UserModel[] } {
  return {
    items: [
      {
        user_model_id: '00000000-0000-0000-0000-0000000000c1',
        provider_credential_id: '00000000-0000-0000-0000-0000000000d1',
        provider_kind: 'anthropic',
        provider_model_name: 'claude-haiku-4-5-20251001',
        context_length: 200_000,
        alias: 'Haiku 4.5',
        is_active: true,
        is_favorite: true,
        capability_flags: { chat: true },
        tags: [],
        created_at: '2026-04-01T00:00:00Z',
      },
      {
        user_model_id: '00000000-0000-0000-0000-0000000000c2',
        provider_credential_id: '00000000-0000-0000-0000-0000000000d1',
        provider_kind: 'openai',
        provider_model_name: 'gpt-5-mini',
        context_length: 128_000,
        alias: null,
        is_active: true,
        is_favorite: false,
        capability_flags: { chat: true },
        tags: [],
        created_at: '2026-04-02T00:00:00Z',
      },
    ],
  };
}

export function userModelsFixtureEmbedding(): { items: UserModel[] } {
  return {
    items: [
      {
        user_model_id: '00000000-0000-0000-0000-0000000000c3',
        provider_credential_id: '00000000-0000-0000-0000-0000000000d2',
        provider_kind: 'ollama',
        provider_model_name: 'bge-m3',
        context_length: 8192,
        alias: null,
        is_active: true,
        is_favorite: true,
        capability_flags: { embedding: true },
        tags: [],
        created_at: '2026-04-01T00:00:00Z',
      },
      {
        user_model_id: '00000000-0000-0000-0000-0000000000c4',
        provider_credential_id: '00000000-0000-0000-0000-0000000000d1',
        provider_kind: 'openai',
        provider_model_name: 'text-embedding-3-small',
        context_length: 8191,
        alias: null,
        is_active: true,
        is_favorite: false,
        capability_flags: { embedding: true },
        tags: [],
        created_at: '2026-04-02T00:00:00Z',
      },
    ],
  };
}

/** Merge of chat + embedding fixtures — use when a single MSW handler
 *  must satisfy both parent dropdowns simultaneously. Realistic enough
 *  for preview; stories don't need production filter fidelity. */
export function userModelsFixtureAll(): { items: UserModel[] } {
  return {
    items: [
      ...userModelsFixtureChat().items,
      ...userModelsFixtureEmbedding().items,
    ],
  };
}
