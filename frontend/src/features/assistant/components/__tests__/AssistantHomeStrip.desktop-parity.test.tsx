// A2 (desktop parity) — the audit's HIGH gap #1/#2: Memory/recall, Journal, Correct, Forget and Erase
// were mounted ONLY in the mobile dock, so a desktop user could not browse memory, read past journal,
// forget a person, or erase their data — the last two being the data-rights controls the first-run
// promises. This test proves those capabilities are now REACHABLE from the desktop home strip.
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';
import type { GlossaryEntitySummary } from '@/features/glossary/types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
}));
vi.mock('@/auth', () => ({ useAuth: () => ({ user: { display_name: 'Claude', email: 'c@x.dev' } }) }));
vi.mock('../../context/AssistantContext', () => ({
  useAssistant: () => ({
    bookId: 'book-1',
    projectId: 'proj-1',
    consentEnabled: false,
    consentSaving: false,
    setConsent: vi.fn(),
    reprovision: vi.fn(),
    endOfDay: { status: 'idle', entry: null, error: null, keeping: false, trigger: vi.fn(), keep: vi.fn() },
    captureRail: { entities: [], loading: false, refresh: vi.fn() },
  }),
}));
// The strip's other cards are idle/empty here — the parity capabilities are what we assert.
vi.mock('../../hooks/useDiaryFactInbox', () => ({
  useDiaryFactInbox: () => ({ facts: [], isLoading: false, error: null, pendingId: null, confirm: vi.fn(), reject: vi.fn(), refetch: vi.fn() }),
}));
vi.mock('../../hooks/useReflection', () => ({ useReflection: () => ({ reflection: null, patterns: [], dismiss: vi.fn() }) }));
vi.mock('../../hooks/useScorecards', () => ({ useScorecards: () => ({ latest: null }) }));
vi.mock('../../hooks/useTimezone', () => ({ useTimezone: () => ({ needsConfirm: false, detected: 'UTC', saving: false, confirm: vi.fn() }) }));

const person = {
  entity_id: 'e1', display_name: 'Minh', short_description: 'colleague',
  kind: { code: 'colleague', name: 'Colleague' },
} as unknown as GlossaryEntitySummary;

const handleForget = vi.fn().mockResolvedValue({ forgotten: true });
const handleEraseAll = vi.fn().mockResolvedValue(true);
vi.mock('../../hooks/useAssistantMemory', () => ({
  useAssistantMemory: () => ({
    journal: { entries: [], loading: false, error: null, refresh: vi.fn() },
    memory: { entities: [person], loading: false, error: null, search: '', setSearch: vi.fn(), refresh: vi.fn() },
    correction: { correctingId: null },
    forgetEntity: { forgettingName: null },
    eraseAll: { erasing: false },
    handleCorrect: vi.fn(),
    handleForget,
    handleEraseAll,
  }),
}));

import { AssistantHomeStrip } from '../AssistantHomeStrip';

function renderStrip() {
  return render(
    <MemoryRouter initialEntries={['/assistant']}>
      <AssistantHomeStrip />
    </MemoryRouter>,
  );
}

describe('AssistantHomeStrip — desktop parity (A2)', () => {
  it('surfaces Journal + Memory affordances on desktop (were mobile-only)', () => {
    renderStrip();
    expect(screen.getByTestId('assistant-open-journal')).toBeTruthy();
    expect(screen.getByTestId('assistant-open-memory')).toBeTruthy();
  });

  it('opening Memory reveals recall + the FORGET and ERASE data-rights controls on desktop', async () => {
    renderStrip();
    fireEvent.click(screen.getByTestId('assistant-open-memory'));

    // The memory sheet opens with the remembered person + the recall search box.
    await waitFor(() => expect(screen.getByTestId('memory-sheet')).toBeTruthy());
    expect(screen.getByText('Minh')).toBeTruthy();
    expect(screen.getByTestId('memory-search')).toBeTruthy();

    // Forget-a-person is reachable (the first-run's "forget anyone" promise, now on desktop).
    expect(screen.getByTestId('memory-forget-e1')).toBeTruthy();
    // Erase-everything danger-zone is reachable (the "erase in one tap" promise, now on desktop).
    expect(screen.getByTestId('memory-erase-all')).toBeTruthy();
  });

  it('the desktop erase danger-zone drives the shared erase handler (two-step confirm)', async () => {
    renderStrip();
    fireEvent.click(screen.getByTestId('assistant-open-memory'));
    await waitFor(() => expect(screen.getByTestId('memory-erase-all-open')).toBeTruthy());

    fireEvent.click(screen.getByTestId('memory-erase-all-open')); // step 1: reveal confirm
    expect(handleEraseAll).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('memory-erase-all-do')); // step 2: confirm
    expect(handleEraseAll).toHaveBeenCalledOnce();
  });
});
