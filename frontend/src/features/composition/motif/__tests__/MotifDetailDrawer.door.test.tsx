// F3 stage 2 — the DOOR onto the motif editor.
//
// F10 shipped this exact shape one layer over: `MotifEditorForm` is fine and directly tested, but
// the only route to it is a four-term predicate in the drawer —
//
//     {motif && !readOnly && !editing && token && ( <button data-testid="motif-detail-edit" …
//
// — and `motif-detail-edit` had ZERO references anywhere outside the component. Every term is a way
// the door can silently vanish while the editor's own suite stays green, which is precisely how the
// four advisory PlanForge editors became dead UI: the leaf was tested, the gate never was.
//
// `readOnly` is not a static prop either. It is `isReadOnly(motif, meUserId)`, which was changed
// this same session so a `book_shared` row returns false — i.e. a shared-to-the-book motif became
// editable. That change's user-visible effect lives HERE, at the door, and nothing asserted it.
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/api', () => ({ apiJson: vi.fn(), apiBase: () => '' }));
// The graph section fires its own queries and is not what this file is about.
vi.mock('../components/MotifGraphSection', () => ({ MotifGraphSection: () => null }));

import { MotifDetailDrawer } from '../components/MotifDetailDrawer';
import { isReadOnly } from '../simpleMode';
import type { Motif } from '../types';

const ME = 'user-1';

// Every field of the real `Motif`, not a cast-away subset. The first version of this fixture used
// `as Motif` over a partial and the drawer died in `useMotifEditor` on `m.roles.map` — the cast
// silenced exactly the check that would have caught it. Fields taken from the type, not from what
// the component happens to touch.
function motif(over: Partial<Motif> = {}): Motif {
  return {
    id: 'm1', owner_user_id: ME, book_id: null, book_shared: false,
    code: 'ash', language: 'en', visibility: 'private', kind: 'situation',
    category: null, name: 'The Wet Ink', summary: 'ink that will not dry',
    genre_tags: [], roles: [], beats: [], preconditions: [], effects: [],
    tension_target: null, emotion_target: null, examples: [],
    abstraction_confidence: null, source: 'authored', source_version: null,
    judge_score: null, mining_support: null, status: 'active', version: 1,
    ...over,
  };
}

function draw(over: Partial<Motif> = {}, props: Record<string, unknown> = {}) {
  const m = motif(over);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MotifDetailDrawer
        motif={m}
        meUserId={ME}
        readOnly={isReadOnly(m, ME)}   // the REAL predicate, not a hand-set boolean
        token="tok"
        onClose={() => {}}
        onClone={() => {}}
        {...props}
      />
    </QueryClientProvider>,
  );
  return m;
}

describe('MotifDetailDrawer — the edit door', () => {
  it('an OWNED motif shows the door', () => {
    draw();
    expect(screen.getByTestId('motif-detail-edit')).toBeTruthy();
  });

  it('a BOOK-SHARED motif shows the door — the session fix, asserted where a user would see it', () => {
    // `isReadOnly` returns false for `book_shared`, so a motif shared into the book is editable by
    // its collaborators. That is a behaviour change with no visible proof unless the DOOR is
    // asserted: the leaf function's unit test cannot tell you the button rendered.
    draw({ owner_user_id: 'someone-else', visibility: 'shared', book_shared: true });
    expect(screen.getByTestId('motif-detail-edit')).toBeTruthy();
  });

  it("someone else's shared TEMPLATE shows no door, and SAYS why", () => {
    // The important half is the second clause. A missing button with no explanation is the
    // affordance-with-no-path bug; the drawer must offer clone-to-edit instead of going quiet.
    draw({ owner_user_id: 'someone-else', visibility: 'shared', book_shared: false });
    expect(screen.queryByTestId('motif-detail-edit')).toBeNull();
    expect(screen.getByTestId('motif-detail-readonly')).toBeTruthy();   // it explains itself…
    expect(screen.getByTestId('motif-detail-clone')).toBeTruthy();      // …and offers the way out
  });

  it('no token → no door (a term that can silently close it)', () => {
    // Documented rather than endorsed: with no token the button disappears with no explanation at
    // all, unlike the shared-template case above. Pinned so the behaviour is a decision, not a
    // surprise — see the note in the session handoff.
    draw({}, { token: null });
    expect(screen.queryByTestId('motif-detail-edit')).toBeNull();
  });

  it('no motif yet (loading) → no door, and no crash', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MotifDetailDrawer
          motif={null} meUserId={ME} readOnly={false} isLoading token="tok"
          onClose={() => {}} onClone={() => {}}
        />
      </QueryClientProvider>,
    );
    expect(screen.queryByTestId('motif-detail-edit')).toBeNull();
  });

  it('the door actually OPENS the editor, and closes behind itself', () => {
    // The whole point of a door. Asserting the button exists proves nothing if clicking it does
    // not swap the editor in — and the editor replaces the detail body, so its absence is visible.
    draw();
    fireEvent.click(screen.getByTestId('motif-detail-edit'));
    expect(screen.queryByTestId('motif-detail-edit')).toBeNull();  // `editing` closes the door
    expect(screen.getByTestId('motif-editor-name')).toBeTruthy();  // …and the form is in
  });
});
