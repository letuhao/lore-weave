// 24 PH21 — the unplanned tray. The load-bearing case is the DEGRADED one: `chapters === null`
// must render "unknown", never an empty/absent tray, because an empty tray asserts "nothing is
// unplanned" about something the server explicitly said it could not compute (absent ≠ zero).
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { UnplannedTray } from '../UnplannedTray';

const chapter = (n: number) => ({
  chapter_id: `ch-${n}`,
  title: `Chương ${n}`,
  sort_order: n,
});

describe('UnplannedTray (PH21)', () => {
  it('renders nothing when there are no unplanned chapters AND we know it', () => {
    render(<UnplannedTray chapters={[]} total={0} onOpenChapter={vi.fn()} />);
    expect(screen.queryByTestId('plan-hub-unplanned-tray')).toBeNull();
  });

  it('DEGRADED (null) renders the unknown state — not an empty tray, and not hidden', () => {
    render(<UnplannedTray chapters={null} total={0} onOpenChapter={vi.fn()} />);
    // it must be VISIBLE (hiding it would look exactly like "nothing unplanned")…
    expect(screen.getByTestId('plan-hub-unplanned-tray')).toBeTruthy();
    // …and it must say it does not know, rather than showing a green-looking 0.
    expect(screen.getByTestId('plan-hub-unplanned-unknown')).toBeTruthy();
  });

  it('shows the EXACT count and lists the chapters when expanded', () => {
    render(
      <UnplannedTray chapters={[chapter(41), chapter(42)]} total={2} onOpenChapter={vi.fn()} />,
    );
    expect(screen.getByText('2')).toBeTruthy();
    fireEvent.click(screen.getByTestId('plan-hub-unplanned-toggle'));
    expect(screen.getAllByTestId('plan-hub-unplanned-row')).toHaveLength(2);
    expect(screen.getByText('Chương 41')).toBeTruthy();
  });

  it('a row opens the chapter in the EDITOR (an unplanned chapter has no spec node to select)', () => {
    const onOpen = vi.fn();
    render(<UnplannedTray chapters={[chapter(41)]} total={1} onOpenChapter={onOpen} />);
    fireEvent.click(screen.getByTestId('plan-hub-unplanned-toggle'));
    fireEvent.click(screen.getByTestId('plan-hub-unplanned-row'));
    expect(onOpen).toHaveBeenCalledWith('ch-41'); // the BOOK chapter_id, not an outline-node id
  });

  it('a server-capped list reports the remainder — the count stays exact (OUT-5)', () => {
    // 3 rows shipped, 250 actually unplanned.
    render(
      <UnplannedTray
        chapters={[chapter(1), chapter(2), chapter(3)]}
        total={250}
        onOpenChapter={vi.fn()}
      />,
    );
    expect(screen.getByText('250')).toBeTruthy(); // exact count, not the page length
    fireEvent.click(screen.getByTestId('plan-hub-unplanned-toggle'));
    expect(screen.getByTestId('plan-hub-unplanned-capped')).toBeTruthy();
  });
});
