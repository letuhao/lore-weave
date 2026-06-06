import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// M5a — the "needs review" badge surfaces the V3 quality rollup.
// M5b — the publish quality-gate holds a flagged version behind a confirm.

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok-1' }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));

const { getChapterVersion, setActiveVersion } = vi.hoisted(() => ({
  getChapterVersion: vi.fn(), setActiveVersion: vi.fn(),
}));
vi.mock('../../api', () => ({
  versionsApi: { getChapterVersion, setActiveVersion },
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
  beforeEach(() => {
    getChapterVersion.mockReset();
    setActiveVersion.mockReset();
    setActiveVersion.mockResolvedValue({ chapter_id: 'c1', target_language: 'vi', active_id: 'v1' });
  });

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

  it('M5b: holds publish behind a confirm when flagged, then acknowledges', async () => {
    getChapterVersion.mockResolvedValue({ ...baseVersion, unresolved_high_count: 3 });
    renderViewer();
    fireEvent.click(await screen.findByText('viewer.set_active'));
    // Confirm dialog opens; nothing published yet.
    expect(await screen.findByText('viewer.publish_anyway')).toBeInTheDocument();
    expect(setActiveVersion).not.toHaveBeenCalled();
    // Acknowledge → publishes with acknowledgeIssues=true.
    fireEvent.click(screen.getByText('viewer.publish_anyway'));
    await waitFor(() =>
      expect(setActiveVersion).toHaveBeenCalledWith('tok-1', 'c1', 'v1', true));
  });

  it('M5b: publishes directly (no confirm) when not flagged', async () => {
    getChapterVersion.mockResolvedValue({ ...baseVersion, unresolved_high_count: 0 });
    renderViewer();
    fireEvent.click(await screen.findByText('viewer.set_active'));
    await waitFor(() =>
      expect(setActiveVersion).toHaveBeenCalledWith('tok-1', 'c1', 'v1', false));
    expect(screen.queryByText('viewer.publish_anyway')).toBeNull();
  });
});
