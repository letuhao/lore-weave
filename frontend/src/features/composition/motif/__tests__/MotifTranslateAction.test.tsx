// The language row + the paid translate door (spec 2026-07-29-motif-i18n §5).
//
// Two things are worth pinning here, and neither is the happy path.
//
// 1. The DOOR. Three cycles landed the storage, the resolution and the 17 platform
//    locales, and a user still could not translate their own motif at all: the policy
//    ("we never spend your tokens without asking") was implemented only in the half that
//    refuses. So "you may buy this" and "you may NOT, and here is why" are both asserted,
//    per tier — a missing affordance with no explanation is the bug this repo keeps
//    re-learning, and an affordance that always 403s is worse than none.
//
// 2. The row must never be INERT. It is easy to ship a badge that renders a field the
//    server never populates on this route; the drawer reads the motif AS AUTHORED, so
//    the language state comes from the translations inventory, and these tests assert
//    against that data rather than against `text_fallback`, which this route does not set.
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('@/api', () => ({ apiJson: vi.fn(), apiBase: () => '' }));
// The model picker mounts an auth provider chain; the buy form is disclosed behind a
// click and is not what these tests are about.
vi.mock('../../../campaigns/components/ModelRolePicker', () => ({
  ModelRolePicker: () => null,
}));

// `vi.mock` is hoisted above the file body, so anything its factory closes over has to be
// hoisted too.
const { motifTranslations, language } = vi.hoisted(() => ({
  motifTranslations: vi.fn(), language: { current: 'vi' },
}));

// The reader's UI language IS the input here: "is your language missing?" is meaningless
// without one, and a suite that leaves it at 'en' against an en-authored motif silently
// tests nothing. `t` echoes its defaultValue so the copy assertions below read the real
// strings rather than key names.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_k: string, o?: { defaultValue?: string } & Record<string, unknown>) =>
      (o?.defaultValue ?? '').replace(/\{\{(\w+)\}\}/g, (_m, k) => String(o?.[k] ?? '')),
    i18n: { get language() { return language.current; } },
  }),
}));
vi.mock('../api', async (orig) => {
  const actual = await orig<typeof import('../api')>();
  return { ...actual, motifApi: { ...actual.motifApi, motifTranslations } };
});

import { MotifTranslateAction } from '../components/MotifTranslateAction';
import type { Motif } from '../types';

const ME = 'user-1';

function motif(over: Partial<Motif> = {}): Motif {
  return {
    id: 'm1', owner_user_id: ME, book_id: null, book_shared: false,
    code: 'ash', original_language: 'en', visibility: 'private', kind: 'situation',
    category: null, name: 'The Wet Ink', summary: 'ink that will not dry',
    genre_tags: [], roles: [], beats: [], preconditions: [], effects: [],
    tension_target: null, emotion_target: null, examples: [],
    abstraction_confidence: null, source: 'authored', source_version: null,
    judge_score: null, mining_support: null, status: 'active', version: 1,
    ...over,
  };
}

function renderIt(props: Partial<React.ComponentProps<typeof MotifTranslateAction>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MotifTranslateAction motif={motif()} canTranslate token="t" {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  language.current = 'vi';
  motifTranslations.mockReset();
  motifTranslations.mockResolvedValue({ original_language: 'en', translations: [] });
});

describe('the language is always stated', () => {
  it('names the language the motif was AUTHORED in', async () => {
    renderIt();
    expect(await screen.findByTestId('motif-language-current')).toHaveTextContent('English');
  });

  it('says when the reader\'s language is missing, rather than showing nothing', async () => {
    // The drawer shows the original; a Vietnamese reader must be told that is what they
    // are looking at. Silence here is the exact bug the whole i18n layer replaces.
    renderIt();
    expect(await screen.findByTestId('motif-language-fallback')).toBeInTheDocument();
  });

  it('lists an existing translation, and flags one made from older source', async () => {
    motifTranslations.mockResolvedValue({
      original_language: 'en',
      translations: [
        { language_code: 'vi', source: 'authored', translated_by: null, updated_at: null, stale: false },
        { language_code: 'ja', source: 'machine', translated_by: 'm-1', updated_at: null, stale: true },
      ],
    });
    renderIt();
    expect(await screen.findByTestId('motif-language-have-vi')).toBeInTheDocument();
    const ja = screen.getByTestId('motif-language-have-ja');
    expect(ja).toHaveTextContent(/outdated/i);
  });
});

describe('the buy door', () => {
  it('OPENS for a motif you own', async () => {
    renderIt();
    expect(await screen.findByTestId('motif-translate-open')).toBeInTheDocument();
  });

  it('OPENS for a book-SHARED motif a collaborator may edit', async () => {
    // The server allows `book_shared AND book_id = X` with EDIT on the book. Gating the
    // UI on ownership would have shut every collaborator out of a capability the backend
    // grants — a permission with no path to it is the same dead capability as no
    // permission. `canTranslate` is the drawer's own `!readOnly`, which is exactly this set.
    renderIt({
      motif: motif({ owner_user_id: 'user-2', book_shared: true, book_id: 'b1' }),
      canTranslate: true,
      bookId: 'b1',
    });
    expect(await screen.findByTestId('motif-translate-open')).toBeInTheDocument();
  });

  it('states that nothing is translated automatically — the policy, at the point of spend', async () => {
    renderIt();
    expect(await screen.findByTestId('motif-language')).toHaveTextContent(/never translated automatically/i);
  });

  it('is CLOSED for a built-in motif, and says the built-ins are already free', async () => {
    // Tenancy: a `motif_translation` row on a system motif is System tier. Letting a
    // regular user write one is the kinds bug. The refusal has to be legible, not blank.
    renderIt({ motif: motif({ owner_user_id: null }), canTranslate: false });
    expect(await screen.findByTestId('motif-language-not-yours'))
      .toHaveTextContent(/every supported language/i);
    expect(screen.queryByTestId('motif-translate-open')).toBeNull();
  });

  it('is CLOSED for someone else\'s public motif, and points at adopt', async () => {
    renderIt({ motif: motif({ owner_user_id: 'user-2', visibility: 'public' }), canTranslate: false });
    expect(await screen.findByTestId('motif-language-not-yours')).toHaveTextContent(/adopt/i);
    expect(screen.queryByTestId('motif-translate-open')).toBeNull();
  });

  it('is CLOSED without a session, rather than opening a flow that cannot mint', async () => {
    renderIt({ token: null });
    expect(await screen.findByTestId('motif-language')).toBeInTheDocument();
    expect(screen.queryByTestId('motif-translate-open')).toBeNull();
  });
});
