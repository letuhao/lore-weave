import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

// M5a — the "needs review" badge surfaces the V3 quality rollup
// (unresolved_high_count) in the translation viewer toolbar.

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok-1' }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));

const { getChapterVersion } = vi.hoisted(() => ({ getChapterVersion: vi.fn() }));
vi.mock('../../api', () => ({
  versionsApi: { getChapterVersion, setActiveVersion: vi.fn() },
}));

import { TranslationViewer } from '../TranslationViewer';

const baseVersion = {
  id: 'v1', job_id: 'j1', chapter_id: 'c1', book_id: 'b1', owner_user_id: 'u1',
  version_num: 1, status: 'completed', translated_body: 'Hello world',
  translated_body_json: null, translated_body_format: 'text',
  source_language: 'en', target_language: 'vi', input_tokens: 10, output_tokens: 8,
  usage_log_id: null, error_message: null, started_at: null, finished_at: null,
  created_at: '2026-01-01', quality_score: 72, qa_rounds_used: 2,
};

function renderViewer() {
  return render(
    <TranslationViewer chapterId="c1" versionId="v1" isActive={false} onSetActive={vi.fn()} />,
  );
}

describe('TranslationViewer needs-review badge', () => {
  beforeEach(() => getChapterVersion.mockReset());

  it('shows the badge when there are unresolved high-severity issues', async () => {
    getChapterVersion.mockResolvedValue({ ...baseVersion, unresolved_high_count: 3 });
    renderViewer();
    expect(await screen.findByTitle('viewer.needs_review_title')).toBeInTheDocument();
  });

  it('hides the badge when there are no unresolved high-severity issues', async () => {
    getChapterVersion.mockResolvedValue({ ...baseVersion, unresolved_high_count: 0 });
    renderViewer();
    // wait for content to render, then assert the badge is absent
    await screen.findByText('Hello world');
    expect(screen.queryByTitle('viewer.needs_review_title')).toBeNull();
  });
});
