import { beforeEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LanguageStatusDots } from './LanguageStatusDots';
import type { CoverageCell } from '@/features/translation/versionsApi';

const BOOK_ID = 'book-1';
const CHAPTER_ID = 'chapter-1';

const makeCell = (overrides: Partial<CoverageCell> = {}): CoverageCell => ({
  has_active: false,
  active_version_num: null,
  latest_version_num: null,
  latest_status: null,
  version_count: 0,
  ...overrides,
});

const renderDots = (coverage: Record<string, CoverageCell> | undefined) =>
  render(
    <MemoryRouter>
      <LanguageStatusDots bookId={BOOK_ID} chapterId={CHAPTER_ID} coverage={coverage} />
    </MemoryRouter>,
  );

describe('LanguageStatusDots', () => {
  beforeEach(() => { cleanup(); });

  // ── Empty / missing ───────────────────────────────────────────────────────

  it('renders "—" when coverage is undefined', () => {
    renderDots(undefined);
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('renders "—" when coverage is empty object', () => {
    renderDots({});
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('renders no links when coverage is empty', () => {
    renderDots({});
    expect(screen.queryAllByRole('link')).toHaveLength(0);
  });

  // ── Link rendering ────────────────────────────────────────────────────────

  it('renders one link per language', () => {
    renderDots({
      vi: makeCell({ has_active: true, active_version_num: 1, version_count: 1, latest_status: 'completed', latest_version_num: 1 }),
      zh: makeCell({ version_count: 1, latest_status: 'completed', latest_version_num: 1 }),
    });
    expect(screen.getAllByRole('link')).toHaveLength(2);
  });

  it('links navigate to chapter translations page with lang param', () => {
    renderDots({
      vi: makeCell({ has_active: true, active_version_num: 1, version_count: 1, latest_status: 'completed', latest_version_num: 1 }),
    });
    const link = screen.getByRole('link');
    expect(link.getAttribute('href')).toBe(
      `/books/${BOOK_ID}/chapters/${CHAPTER_ID}/translations?lang=vi`,
    );
  });

  // ── Tooltips ──────────────────────────────────────────────────────────────

  it('title shows "v{N} active" when has_active=true', () => {
    renderDots({
      vi: makeCell({ has_active: true, active_version_num: 2, version_count: 2, latest_status: 'completed', latest_version_num: 2 }),
    });
    expect(screen.getByRole('link').getAttribute('title')).toBe('vi: v2 active');
  });

  it('title shows version count info when has_active=false and versions exist', () => {
    renderDots({
      zh: makeCell({ has_active: false, version_count: 3, latest_status: 'completed', latest_version_num: 3 }),
    });
    const title = screen.getByRole('link').getAttribute('title') ?? '';
    expect(title).toContain('3 version(s)');
    expect(title).toContain('not set active');
  });

  it('title shows "no translation" when version_count=0', () => {
    renderDots({
      fr: makeCell({ has_active: false, version_count: 0, latest_status: null }),
    });
    expect(screen.getByRole('link').getAttribute('title')).toBe('fr: no translation');
  });

  // ── Colors ────────────────────────────────────────────────────────────────

  it('applies green color for active language', () => {
    renderDots({
      vi: makeCell({ has_active: true, active_version_num: 1, version_count: 1, latest_status: 'completed', latest_version_num: 1 }),
    });
    expect(screen.getByRole('link').className).toContain('text-green-600');
  });

  it('applies blue color for translated (not active) language', () => {
    renderDots({
      zh: makeCell({ has_active: false, version_count: 1, latest_status: 'completed', latest_version_num: 1 }),
    });
    expect(screen.getByRole('link').className).toContain('text-blue-600');
  });

  it('applies amber color for running language', () => {
    renderDots({
      ja: makeCell({ has_active: false, version_count: 1, latest_status: 'running', latest_version_num: 1 }),
    });
    expect(screen.getByRole('link').className).toContain('text-amber-600');
  });
});
