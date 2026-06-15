import type { Page, Locator } from '@playwright/test';
import { expect } from '@playwright/test';

// Creation-unblock RAID (D-WORLD-PROJECT-BACKLINK / G3) — the knowledge project
// detail Overview, which cross-links to its book (by title) and, when that book
// is grouped into a world, the world.
export class KnowledgeProjectOverviewPage {
  readonly page: Page;
  readonly overview: Locator;
  readonly bookLink: Locator;
  readonly worldLink: Locator;

  constructor(page: Page) {
    this.page = page;
    this.overview = page.getByTestId('shell-overview');
    this.bookLink = page.getByTestId('overview-book-link');
    this.worldLink = page.getByTestId('overview-world-link');
  }

  async goto(projectId: string): Promise<void> {
    await this.page.goto(`/knowledge/projects/${projectId}/overview`);
    await expect(this.overview).toBeVisible();
  }
}
