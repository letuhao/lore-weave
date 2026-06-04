import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { PublishControl } from '../components/PublishControl';
import editorEn from '@/i18n/locales/en/editor.json';

// ── mocks ────────────────────────────────────────────────────────────
const h = vi.hoisted(() => ({
  publishChapter: vi.fn(),
  unpublishChapter: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock('@/features/books/api', () => ({
  booksApi: {
    publishChapter: (...a: unknown[]) => h.publishChapter(...a),
    unpublishChapter: (...a: unknown[]) => h.unpublishChapter(...a),
  },
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('sonner', () => ({ toast: { success: (m: string) => h.toastSuccess(m), error: (m: string) => h.toastError(m) } }));

const renderControl = (over: Record<string, unknown> = {}) => {
  const onChanged = vi.fn();
  const utils = render(
    <PublishControl
      token="tok"
      bookId="b1"
      chapterId="c1"
      draftVersion={4}
      editorialStatus="draft"
      onChanged={onChanged}
      {...over}
    />,
  );
  return { ...utils, onChanged };
};

beforeEach(() => {
  Object.values(h).forEach((fn) => fn.mockReset());
});

describe('PublishControl (CM-FE)', () => {
  it('shows the draft badge + a Publish action on a draft chapter', () => {
    renderControl({ editorialStatus: 'draft' });
    expect(screen.getByTestId('editorial-badge').textContent).toContain('publish.draft_badge');
    expect(screen.getByText('publish.publish')).toBeTruthy();
    // no Unpublish on a draft chapter
    expect(screen.queryByText('publish.unpublish')).toBeNull();
  });

  it('shows Published badge + Re-publish + Unpublish on a published chapter', () => {
    renderControl({ editorialStatus: 'published' });
    expect(screen.getByTestId('editorial-badge').textContent).toContain('publish.published_badge');
    expect(screen.getByText('publish.republish')).toBeTruthy();
    expect(screen.getByText('publish.unpublish')).toBeTruthy();
  });

  it('disables Publish when the editor has unsaved changes (must save first)', () => {
    renderControl({ editorialStatus: 'draft', dirty: true });
    expect((screen.getByText('publish.publish').closest('button') as HTMLButtonElement).disabled).toBe(true);
  });

  it('publishes with expected_draft_version and refetches on success', async () => {
    h.publishChapter.mockResolvedValue({});
    const { onChanged } = renderControl({ editorialStatus: 'draft' });
    fireEvent.click(screen.getByText('publish.publish'));
    await waitFor(() => expect(h.publishChapter).toHaveBeenCalledWith('tok', 'b1', 'c1', 4));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(h.toastSuccess).toHaveBeenCalledWith('publish.published_toast');
  });

  it('on a 409 draft conflict, shows the conflict toast and does NOT refetch', async () => {
    h.publishChapter.mockRejectedValue(Object.assign(new Error('conflict'), { code: 'CHAPTER_DRAFT_CONFLICT' }));
    const { onChanged } = renderControl({ editorialStatus: 'draft' });
    fireEvent.click(screen.getByText('publish.publish'));
    await waitFor(() => expect(h.toastError).toHaveBeenCalledWith('publish.conflict_toast'));
    expect(onChanged).not.toHaveBeenCalled();
  });

  it('renders nothing until editorial_status is known (pre-load / pre-CM1 BE)', () => {
    const { container } = renderControl({ editorialStatus: undefined });
    expect(container.firstChild).toBeNull();
  });

  it('treats a bare 409 (no error code) as a draft conflict too', async () => {
    h.publishChapter.mockRejectedValue(Object.assign(new Error('conflict'), { status: 409 }));
    const { onChanged } = renderControl({ editorialStatus: 'draft' });
    fireEvent.click(screen.getByText('publish.publish'));
    await waitFor(() => expect(h.toastError).toHaveBeenCalledWith('publish.conflict_toast'));
    expect(onChanged).not.toHaveBeenCalled();
  });

  it('every publish.* i18n key the component references exists in en/editor.json', () => {
    // Regression-lock: the t:k=>k mock can't catch a missing locale key, so
    // assert the real en locale carries every key the component/hook uses.
    const keys = [
      'publish', 'republish', 'unpublish', 'draft_badge', 'published_badge',
      'confirm_title', 'confirm_body', 'published_toast', 'unpublished_toast',
      'conflict_toast', 'save_first',
    ];
    const block = (editorEn as Record<string, Record<string, string>>).publish;
    keys.forEach((k) => expect(block?.[k], `missing editor.publish.${k}`).toBeTruthy());
  });

  it('unpublish opens a confirm dialog; confirming retracts canon + refetches', async () => {
    h.unpublishChapter.mockResolvedValue({});
    const { onChanged } = renderControl({ editorialStatus: 'published' });

    // Click toolbar Unpublish → confirm dialog opens (Radix-portaled to document).
    fireEvent.click(screen.getByText('publish.unpublish'));
    await screen.findByText('publish.confirm_title');

    // The dialog's confirm button also reads 'publish.unpublish'; pick the one
    // inside the portal (the last match) and click it.
    const matches = screen.getAllByText('publish.unpublish');
    fireEvent.click(matches[matches.length - 1].closest('button') as HTMLButtonElement);

    await waitFor(() => expect(h.unpublishChapter).toHaveBeenCalledWith('tok', 'b1', 'c1'));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(h.toastSuccess).toHaveBeenCalledWith('publish.unpublished_toast');
  });
});
