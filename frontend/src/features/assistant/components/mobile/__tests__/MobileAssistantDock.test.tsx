// M1 — the mobile dock binds the reused hooks and exposes the thumb-zone actions. Guards:
// End-my-day is a VISIBLE button (not a buried gesture) that triggers the distiller; the Today
// button opens the addressable Today sheet; the review badge counts captures + pending facts.
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
}));

const trigger = vi.fn().mockResolvedValue(undefined);
const refetch = vi.fn();
const railRefresh = vi.fn();
const journalRefresh = vi.fn();

vi.mock('../../../context/AssistantContext', () => ({
  useAssistant: () => ({
    bookId: 'book-1',
    projectId: 'proj-1',
    consentEnabled: false,
    consentSaving: false,
    setConsent: vi.fn(),
    // endOfDay is now lifted into the context (survives the strip↔dock swap).
    endOfDay: { status: 'idle', entry: null, error: null, keeping: false, trigger, keep: vi.fn() },
    // captureRail is now shared via context (DF2 — one fetch for header + dock + sheet).
    captureRail: {
      entities: [railEntity('e1', 'Alice'), railEntity('e2', 'Bob')],
      loading: false,
      refresh: railRefresh,
    },
  }),
}));
const railEntity = (id: string, name: string) => ({
  entity_id: id,
  display_name: name,
  short_description: null,
  kind: { code: 'colleague', name: 'Colleague' },
});
vi.mock('../../../hooks/useDiaryFactInbox', () => ({
  useDiaryFactInbox: () => ({
    facts: [{ pending_fact_id: 'f1' }],
    isLoading: false,
    error: null,
    pendingId: null,
    confirm: vi.fn(),
    reject: vi.fn(),
    refetch,
  }),
}));
vi.mock('../../../hooks/useReflection', () => ({
  useReflection: () => ({ reflection: null, patterns: [], dismiss: vi.fn() }),
}));
vi.mock('../../../hooks/useScorecards', () => ({
  useScorecards: () => ({ latest: null }),
}));
vi.mock('../../../hooks/useTimezone', () => ({
  useTimezone: () => ({ needsConfirm: false, detected: 'UTC', saving: false, confirm: vi.fn() }),
}));
vi.mock('../../../hooks/useDiaryEntries', () => ({
  useDiaryEntries: () => ({ entries: [], loading: false, error: null, refresh: journalRefresh }),
}));

import { MobileAssistantDock } from '../MobileAssistantDock';

function renderDock() {
  return render(
    <MemoryRouter initialEntries={['/assistant']}>
      <MobileAssistantDock />
    </MemoryRouter>,
  );
}

describe('MobileAssistantDock', () => {
  beforeEach(() => {
    trigger.mockClear();
    refetch.mockClear();
    railRefresh.mockClear();
  });

  it('renders a VISIBLE End my day button that triggers the distiller', () => {
    renderDock();
    const endDay = screen.getByTestId('dock-end-day');
    expect(endDay.textContent).toContain('End my day');
    fireEvent.click(endDay);
    expect(trigger).toHaveBeenCalledTimes(1);
    expect(railRefresh).toHaveBeenCalled();
  });

  it('the Today button opens the addressable Today sheet', () => {
    renderDock();
    expect(screen.queryByTestId('sheet-today')).toBeNull();
    fireEvent.click(screen.getByTestId('dock-today'));
    expect(screen.getByTestId('sheet-today')).toBeTruthy();
  });

  it('the review badge counts captures + pending facts (2 + 1 = 3)', () => {
    renderDock();
    // The badge is inside the Today button; its aria-label states the count.
    expect(screen.getByLabelText('3 to review')).toBeTruthy();
  });

  it('the Journal button opens the addressable Journal sheet', () => {
    renderDock();
    fireEvent.click(screen.getByTestId('dock-journal'));
    expect(screen.getByTestId('sheet-journal')).toBeTruthy();
    expect(journalRefresh).toHaveBeenCalled();
  });
});
