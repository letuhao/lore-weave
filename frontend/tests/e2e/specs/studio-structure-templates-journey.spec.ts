// S-01 slice B · BLACKBOX — a user reaches the structure-templates panel from empty and CLONES a
// built-in into an editable own copy. This is the anti-shell proof (PO directive): the panel is not
// view-only — a brand-new user with ZERO own structures gets an editable one in one click, and the
// clone is a REAL create that lands as a "mine" row. Structure templates are PER-USER (no book
// scope); we seed a book only because the studio shell needs one to open.
import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, trashBook } from '../helpers/api';
import { StudioPage } from '../pages/StudioPage';

test.describe('@s01 Studio · structure-templates (blackbox: clone from empty)', () => {
  let token: string;
  let bookId: string;
  const stamp = Date.now();

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `E2E structure-templates ${stamp}`);
  });
  test.afterAll(async ({ request }) => {
    if (bookId) await trashBook(request, token, bookId).catch(() => {});
  });
  test.beforeEach(async ({ page }) => { await loginViaUI(page); });

  test('reach the panel, read a built-in, clone it into my own editable tier', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);

    // ── reachable from the palette (F-7 lesson: built ≠ reachable) ──
    await studio.openPanel('structure-templates', 'structure');
    const panel = page.getByTestId('structure-templates');
    await expect(panel, 'the structure-templates panel opens from the palette').toBeVisible();

    // ── the built-ins are listed (the migration seeds 6) ──
    const rows = page.getByTestId('structtpl-row');
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });
    const builtin = page.getByRole('button', { name: 'Save the Cat system' });
    await expect(builtin, 'a built-in structure is listed').toBeVisible();

    // ── select it → its beats render (not just a name list — a real read surface) ──
    await builtin.click();
    await expect(page.getByTestId('structtpl-detail')).toContainText('beats');
    await expect(
      page.getByTestId('structtpl-readonly-note'),
      'a built-in shows the read-only + clone hint, not silent editability',
    ).toBeVisible();

    // ── CLONE (the entry point from empty) → an editable "mine" copy appears ──
    const mineBefore = await page.getByTestId('structtpl-row').filter({ hasText: 'mine' }).count();
    await page.getByTestId('structtpl-clone').click();
    // the fresh copy lands selected + shows as "mine" (no read-only note → it's editable)
    await expect(
      page.getByTestId('structtpl-detail').getByText('mine', { exact: false }).first(),
      'after cloning, the detail shows an OWN (editable) copy — the create landed, not a no-op',
    ).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('structtpl-readonly-note')).toHaveCount(0);
    const mineAfter = await page.getByTestId('structtpl-row').filter({ hasText: 'mine' }).count();
    expect(mineAfter, 'a new "mine" row was added by the clone').toBeGreaterThan(mineBefore);

    await page.screenshot({ path: 'tests/e2e/test-results/structtpl-cloned.png' }).catch(() => {});
  });

  // ── SLICE C · author the beats + save → the edit PERSISTS server-side (not a shell) ──
  test('edit a cloned structure’s beats and save — the change persists across a reopen', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.openPanel('structure-templates', 'structure');

    // clone a built-in to get an own, editable copy (the entry point)
    await page.getByRole('button', { name: 'Kishōtenketsu system' }).click();
    await page.getByTestId('structtpl-clone').click();
    await expect(page.getByTestId('structtpl-beat-editor'), 'an own copy shows the EDITOR, not a read-only list').toBeVisible({ timeout: 10_000 });

    // rename to a UNIQUE name (so re-selection is unambiguous on the shared dev DB) + edit the first
    // beat's label + add a beat — real authoring, not an abstract drawer.
    const uniqueName = `E2E Struct ${stamp}`;
    const marker = `E2E beat ${stamp}`;
    await page.getByTestId('structtpl-name').fill(uniqueName);
    await page.getByTestId('structtpl-beat-label').first().fill(marker);
    const beatsBefore = await page.getByTestId('structtpl-beat-row').count();
    await page.getByTestId('structtpl-beat-add').click();
    await expect(page.getByTestId('structtpl-beat-row')).toHaveCount(beatsBefore + 1);

    // SAVE → OCC update
    await page.getByTestId('structtpl-save').click();
    await expect(page.getByTestId('structtpl-save-error'), 'save must not error').toHaveCount(0);

    // PERSISTENCE proof: navigate away to a built-in, then back to MY renamed template — the editor
    // REMOUNTS and loads from the server, so the marker being there proves the write landed.
    await page.getByRole('button', { name: 'Save the Cat system' }).click();
    await expect(page.getByTestId('structtpl-readonly-note')).toBeVisible();
    await page.getByTestId('structtpl-row').filter({ hasText: uniqueName }).click();
    await expect(
      page.getByTestId('structtpl-beat-label').first(),
      'after a reopen the edited beat label is loaded from the server — the save persisted',
    ).toHaveValue(marker, { timeout: 10_000 });

    await page.screenshot({ path: 'tests/e2e/test-results/structtpl-edited.png' }).catch(() => {});
  });

  // ── SLICE D · archive → restore round-trips (no dead-end soft-delete) ──
  test('archive an own structure then restore it — a clean round-trip, not a dead-end', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.openPanel('structure-templates', 'structure');

    // clone + rename to a unique name so we can track it unambiguously on the shared dev DB
    const uniqueName = `E2E Archive ${stamp}`;
    await page.getByRole('button', { name: 'Story Circle system' }).click();
    await page.getByTestId('structtpl-clone').click();
    await expect(page.getByTestId('structtpl-beat-editor')).toBeVisible({ timeout: 10_000 });
    await page.getByTestId('structtpl-name').fill(uniqueName);
    await page.getByTestId('structtpl-save').click();
    await expect(page.getByTestId('structtpl-save-error')).toHaveCount(0);
    await page.getByTestId('structtpl-row').filter({ hasText: uniqueName }).click();

    // ARCHIVE → it leaves the default (non-archived) list
    await page.getByTestId('structtpl-archive').click();
    await expect(
      page.getByTestId('structtpl-row').filter({ hasText: uniqueName }),
      'after archiving, the template is gone from the default list',
    ).toHaveCount(0, { timeout: 10_000 });

    // toggle "archived" → it reappears, badged archived, and is RESTORABLE (not a dead-end)
    await page.getByTestId('structtpl-show-archived').check();
    const archivedRow = page.getByTestId('structtpl-row').filter({ hasText: uniqueName });
    await expect(archivedRow, 'the archived template is visible under the archived toggle').toBeVisible({ timeout: 10_000 });
    await archivedRow.click();
    await expect(page.getByTestId('structtpl-archived-note')).toBeVisible();

    // RESTORE → back to an active, editable template
    await page.getByTestId('structtpl-restore').click();
    await page.getByTestId('structtpl-show-archived').uncheck();
    await expect(
      page.getByTestId('structtpl-row').filter({ hasText: uniqueName }),
      'after restore, the template is back in the default list',
    ).toBeVisible({ timeout: 10_000 });

    await page.screenshot({ path: 'tests/e2e/test-results/structtpl-archive-restore.png' }).catch(() => {});
  });
});
