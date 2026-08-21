import { test, expect } from '@playwright/test';

const BOOK_ID = 'epub-e2e-book';
const TOKEN = 'epub-e2e-token';

test.describe('EPUB import wizard browser smoke', () => {
  test('authenticated wizard previews nested ToC and completes a mocked durable job', async ({ page }) => {
    test.setTimeout(60_000);
    let jobPolls = 0;

    await page.addInitScript(({ token, bookId }) => {
      localStorage.setItem('lw_auth', JSON.stringify({ accessToken: token, refreshToken: 'epub-refresh' }));
      localStorage.setItem('lw_user', JSON.stringify({
        user_id: 'epub-e2e-user', email: 'epub@example.test', display_name: 'EPUB E2E', avatar_url: null,
      }));
      sessionStorage.setItem('lw:session-id', 'epub-e2e-session');
      void bookId;
    }, { token: TOKEN, bookId: BOOK_ID });

    await page.route('**/v1/**', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname;

      if (path === '/v1/account/profile') {
        return route.fulfill({ json: { user_id: 'epub-e2e-user', email: 'epub@example.test', display_name: 'EPUB E2E', avatar_url: null } });
      }
      if (path === `/v1/books/${BOOK_ID}`) {
        return route.fulfill({ json: {
          book_id: BOOK_ID, owner_user_id: 'epub-e2e-user', access_level: 'owner', title: 'Shadow Corpus Book',
          original_language: 'en', chapter_count: 0, genre_tags: [], lifecycle_state: 'active', visibility: 'private',
        } });
      }
      if (path === `/v1/books/${BOOK_ID}/stats`) {
        return route.fulfill({ json: { total_readers: 0, avg_time_ms: 0, avg_scroll_depth: 0 } });
      }
      if (path === `/v1/books/${BOOK_ID}/chapters`) {
        return route.fulfill({ json: { items: [], total: 0, limit: 20, offset: 0 } });
      }
      if (path === '/v1/books' && request.method() === 'GET') {
        return route.fulfill({ json: { items: [], total: 0 } });
      }
      if (path === `/v1/books/${BOOK_ID}/view`) {
        return route.fulfill({ status: 204, body: '' });
      }
      if (path === '/v1/notifications/stream') {
        return route.fulfill({ status: 200, contentType: 'text/event-stream', body: ': smoke keep-alive\n\n' });
      }
      if (path === '/v1/epub-imports/inspect') {
        return route.fulfill({ json: {
          source_id: 'epub-source',
          navigation_source: 'epub3-nav',
          metadata: { title: 'Nested Shadow Book', creators: ['Test Author'], language: 'en' },
          structure: [{ source_key: 'part', source_href: 'body.xhtml', title: 'Part I', depth: 0, role: 'part', selected: false, children: [
            { source_key: 'one', source_href: 'body.xhtml', title: 'Chapter One', depth: 1, role: 'chapter', selected: true, children: [] },
            { source_key: 'two', source_href: 'body.xhtml', title: 'Chapter Two', depth: 1, role: 'chapter', selected: true, children: [] },
          ] }],
          warnings: [], duplicate_source: false,
        } });
      }
      if (path === '/v1/epub-imports') {
        return route.fulfill({ json: { job_id: 'epub-job', book_id: BOOK_ID, status: 'queued' } });
      }
      if (path === '/v1/import-jobs/epub-job') {
        jobPolls += 1;
        return route.fulfill({ json: {
          job_id: 'epub-job', book_id: BOOK_ID, source_id: 'epub-source', status: jobPolls > 0 ? 'completed_with_warnings' : 'queued',
          progress_total: 2, progress_completed: 2, progress_failed: 0, chapters_created: 2,
          warnings: ['composition_materialization_retry'], errors: [], resumable: false, cancellable: false, rollback_available: true,
        } });
      }
      if (path === '/v1/import-jobs/epub-job/report') {
        return route.fulfill({ json: { job_id: 'epub-job', status: 'completed_with_warnings', chapters_created: 2, warnings: ['composition_materialization_retry'], errors: [] } });
      }
      return route.fulfill({ json: {} });
    });

    await page.goto(`/books/${BOOK_ID}`, { waitUntil: 'commit' });
    await page.waitForLoadState('domcontentloaded').catch(() => {});
    await expect(page.getByTestId('epub-import-open')).toBeVisible({ timeout: 20_000 });
    await page.getByTestId('epub-import-open').click();
    await expect(page.getByTestId('epub-import-dialog')).toBeVisible();

    await page.getByTestId('epub-import-file-input').setInputFiles({
      name: 'nested-shadow.epub', mimeType: 'application/epub+zip', buffer: Buffer.from('PK\u0003\u0004shadow-fixture'),
    });
    await expect(page.getByText('Nested Shadow Book')).toBeVisible();
    await page.getByTestId('epub-import-next').click();
    await expect(page.getByText('2 chapters selected')).toBeVisible();
    await expect(page.getByText('Chapter One')).toBeVisible();
    await expect(page.getByText('Chapter Two')).toBeVisible();

    await page.getByTestId('epub-import-next').click();
    await page.getByTestId('epub-import-strategy-replace_all').check();
    await expect(page.getByTestId('epub-import-next')).toBeDisabled();
    await page.getByTestId('epub-import-replace-confirmation').check();
    await page.getByTestId('epub-import-next').click();

    await expect(page.getByText('completed_with_warnings')).toBeVisible();
    await expect(page.getByTestId('epub-import-report-summary')).toHaveText('2 chapters created · 1 warnings');
    await expect(page.getByTestId('epub-import-report-warnings')).toContainText('composition_materialization_retry');
  });
});
