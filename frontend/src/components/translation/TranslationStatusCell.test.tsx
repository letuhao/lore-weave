import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { deriveCellStatus, TranslationStatusCell } from './TranslationStatusCell';
import type { CoverageCell } from '@/features/translation/versionsApi';

const makeCell = (overrides: Partial<CoverageCell> = {}): CoverageCell => ({
  has_active: false,
  active_version_num: null,
  latest_version_num: null,
  latest_status: null,
  version_count: 0,
  ...overrides,
});

// ── deriveCellStatus ──────────────────────────────────────────────────────────

describe('deriveCellStatus', () => {
  it('returns "none" for null cell', () => {
    expect(deriveCellStatus(null)).toBe('none');
  });

  it('returns "none" for undefined cell', () => {
    expect(deriveCellStatus(undefined)).toBe('none');
  });

  it('returns "none" for zero version_count with no status', () => {
    expect(deriveCellStatus(makeCell({ version_count: 0, latest_status: null }))).toBe('none');
  });

  it('returns "running" when latest_status is "running"', () => {
    expect(deriveCellStatus(makeCell({ latest_status: 'running', version_count: 1 }))).toBe('running');
  });

  it('returns "failed" when latest_status=failed and version_count=1', () => {
    expect(deriveCellStatus(makeCell({ latest_status: 'failed', version_count: 1 }))).toBe('failed');
  });

  it('returns "active" when has_active=true (takes priority over completed)', () => {
    expect(deriveCellStatus(makeCell({
      has_active: true,
      active_version_num: 1,
      latest_status: 'completed',
      version_count: 1,
      latest_version_num: 1,
    }))).toBe('active');
  });

  it('returns "translated" when completed and not active', () => {
    expect(deriveCellStatus(makeCell({
      has_active: false,
      latest_status: 'completed',
      version_count: 1,
      latest_version_num: 1,
    }))).toBe('translated');
  });

  it('returns "partial" when version_count > 0 but not completed', () => {
    expect(deriveCellStatus(makeCell({ version_count: 2, latest_status: 'pending' }))).toBe('partial');
  });

  it('returns "partial" for failed with multiple versions', () => {
    expect(deriveCellStatus(makeCell({ latest_status: 'failed', version_count: 2 }))).toBe('partial');
  });
});

// ── Label logic (LW-72 fix: show v{N} not Nv) ────────────────────────────────

describe('TranslationStatusCell — label', () => {
  beforeEach(() => { cleanup(); });

  it('shows "v2 ✓" when has_active=true with active_version_num=2', () => {
    render(
      <TranslationStatusCell cell={makeCell({
        has_active: true,
        active_version_num: 2,
        latest_status: 'completed',
        version_count: 2,
        latest_version_num: 2,
      })} />,
    );
    expect(screen.getByRole('button').textContent).toContain('v2 ✓');
  });

  it('shows "v3" (not "3v") when has_active=false but latest_version_num=3', () => {
    render(
      <TranslationStatusCell cell={makeCell({
        has_active: false,
        latest_version_num: 3,
        latest_status: 'completed',
        version_count: 3,
      })} />,
    );
    const text = screen.getByRole('button').textContent ?? '';
    expect(text).toContain('v3');
    expect(text).not.toContain('3v');
  });

  it('shows no version label when latest_version_num is null and no active', () => {
    render(
      <TranslationStatusCell cell={makeCell({
        has_active: false,
        latest_version_num: null,
        latest_status: 'completed',
        version_count: 1,
      })} />,
    );
    // Button should render but without "vN" label
    const btn = screen.getByRole('button');
    expect(btn.textContent).not.toMatch(/v\d/);
  });

  it('shows "v1 ✓" for first active version', () => {
    render(
      <TranslationStatusCell cell={makeCell({
        has_active: true,
        active_version_num: 1,
        latest_status: 'completed',
        version_count: 1,
        latest_version_num: 1,
      })} />,
    );
    expect(screen.getByRole('button').textContent).toContain('v1 ✓');
  });
});

// ── Rendering ────────────────────────────────────────────────────────────────

describe('TranslationStatusCell — rendering', () => {
  beforeEach(() => { cleanup(); });

  it('renders dash span (not button) for "none" status', () => {
    render(<TranslationStatusCell cell={null} />);
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('renders button for "active" status', () => {
    render(
      <TranslationStatusCell cell={makeCell({
        has_active: true,
        active_version_num: 1,
        latest_status: 'completed',
        version_count: 1,
        latest_version_num: 1,
      })} />,
    );
    expect(screen.getByRole('button')).toBeInTheDocument();
  });

  it('calls onClick when button is clicked', () => {
    const onClick = vi.fn();
    render(
      <TranslationStatusCell
        cell={makeCell({ has_active: true, active_version_num: 1, latest_status: 'completed', version_count: 1, latest_version_num: 1 })}
        onClick={onClick}
      />,
    );
    fireEvent.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('applies green color class for "active" status', () => {
    render(
      <TranslationStatusCell cell={makeCell({
        has_active: true,
        active_version_num: 1,
        latest_status: 'completed',
        version_count: 1,
        latest_version_num: 1,
      })} />,
    );
    expect(screen.getByRole('button').className).toContain('text-green-600');
  });

  it('applies blue color class for "translated" status', () => {
    render(
      <TranslationStatusCell cell={makeCell({
        has_active: false,
        latest_status: 'completed',
        version_count: 1,
        latest_version_num: 1,
      })} />,
    );
    expect(screen.getByRole('button').className).toContain('text-blue-600');
  });

  it('applies amber color class for "running" status', () => {
    render(
      <TranslationStatusCell cell={makeCell({
        latest_status: 'running',
        version_count: 1,
      })} />,
    );
    expect(screen.getByRole('button').className).toContain('text-amber-600');
  });

  it('applies red color class for "failed" status', () => {
    render(
      <TranslationStatusCell cell={makeCell({
        latest_status: 'failed',
        version_count: 1,
      })} />,
    );
    expect(screen.getByRole('button').className).toContain('text-red-600');
  });
});
