/**
 * Tests for LW-73 timestamp improvements.
 *
 * Both JobsDrawer and VersionSidebar previously used toLocaleDateString()
 * (date only). LW-73 changed both to toLocaleString() with hour + minute.
 *
 * Strategy: render the components with a known ISO timestamp and assert that
 * digits that could only come from the time portion (HH:MM) appear in the DOM.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import { JobsDrawer } from './JobsDrawer';
import { VersionSidebar } from './VersionSidebar';
import type { TranslationJob } from '@/features/translation/api';
import type { LanguageVersionGroup } from '@/features/translation/versionsApi';

// JobsDrawer imports translationApi and Button at module level — mock them
vi.mock('@/features/translation/api', () => ({
  translationApi: { cancelJob: vi.fn() },
}));
vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => (
    <button onClick={onClick}>{children}</button>
  ),
}));

// ── Helpers ───────────────────────────────────────────────────────────────────

const ISO_TS = '2025-04-15T14:35:00.000Z';

function makeJob(overrides: Partial<TranslationJob> = {}): TranslationJob {
  return {
    job_id:              'job-1',
    book_id:             'book-1',
    owner_user_id:       'user-1',
    status:              'completed',
    target_language:     'vi',
    model_source:        'platform_model',
    model_ref:           'model-1',
    system_prompt:       '',
    user_prompt_tpl:     '{chapter_text}',
    compact_model_source: null,
    compact_model_ref:   null,
    compact_system_prompt:   '',
    compact_user_prompt_tpl: '',
    chunk_size_tokens:   2000,
    invoke_timeout_secs: 300,
    chapter_ids:         [],
    total_chapters:      1,
    completed_chapters:  1,
    failed_chapters:     0,
    error_message:       null,
    started_at:          null,
    finished_at:         null,
    created_at:          ISO_TS,
    ...overrides,
  };
}

function makeVersionGroup(): LanguageVersionGroup {
  return {
    target_language: 'vi',
    active_id: null,
    versions: [
      {
        id:            'ver-1',
        version_num:   1,
        job_id:        'job-1',
        status:        'completed',
        is_active:     false,
        model_source:  'platform_model',
        model_ref:     null,
        input_tokens:  100,
        output_tokens: 80,
        created_at:    ISO_TS,
      },
    ],
  };
}

// ── JobsDrawer timestamps ─────────────────────────────────────────────────────

describe('JobsDrawer timestamp', () => {
  beforeEach(() => { cleanup(); });

  it('renders job created_at with time component', () => {
    render(
      <JobsDrawer
        token="t"
        bookId="book-1"
        jobs={[makeJob()]}
        onClose={vi.fn()}
        onJobsChange={vi.fn()}
      />,
    );
    // The rendered timestamp must contain a colon (e.g. "14:35" or "2:35")
    // which is only present in toLocaleString with time, not toLocaleDateString.
    const content = document.body.textContent ?? '';
    expect(content).toMatch(/\d{1,2}:\d{2}/);  // HH:MM pattern
  });
});

// ── VersionSidebar timestamps ─────────────────────────────────────────────────

describe('VersionSidebar timestamp', () => {
  beforeEach(() => { cleanup(); });

  it('renders version created_at with time component', () => {
    render(
      <VersionSidebar
        languages={[makeVersionGroup()]}
        selectedLang="vi"
        onLangChange={vi.fn()}
        selectedVersionId="ver-1"
        onVersionSelect={vi.fn()}
        onRetranslate={vi.fn()}
      />,
    );
    const content = document.body.textContent ?? '';
    expect(content).toMatch(/\d{1,2}:\d{2}/);  // HH:MM pattern
  });
});

// ── formatDate unit test (inline) ──────────────────────────────────────────────
// We test the toLocaleString output shape by running it in Node/jsdom directly.

describe('toLocaleString with hour+minute option', () => {
  it('output contains a colon-separated time fragment', () => {
    const formatted = new Date(ISO_TS).toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
    // Must include a time separator (colon)
    expect(formatted).toMatch(/\d{1,2}:\d{2}/);
  });

  it('output contains the year 2025', () => {
    const formatted = new Date(ISO_TS).toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
    expect(formatted).toContain('2025');
  });

  it('toLocaleDateString does NOT contain a colon (regression guard)', () => {
    const dateOnly = new Date(ISO_TS).toLocaleDateString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
    });
    // Date-only output (Apr 15, 2025) has no colon
    expect(dateOnly).not.toMatch(/\d{1,2}:\d{2}/);
  });
});
