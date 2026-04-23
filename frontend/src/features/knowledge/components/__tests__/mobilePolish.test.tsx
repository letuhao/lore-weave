// C5 (D-K19d-β-01 + D-K19f-ε-01) — mobile polish smoke tests for
// three desktop-shared components. Asserts the responsive classes
// land in the DOM; jsdom can't drive a media query so we can't
// verify the viewport-actually-hides-desktop behaviour here, but
// locking the class NAMES means a regression that drops `md:block`
// or `md:hidden` or the TOUCH_TARGET_MOBILE_ONLY_CLASS composition
// fails these tests.

import { describe, it, expect, vi } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

import type { Entity } from '../../api';

// ── mocks ──────────────────────────────────────────────────────────

const { useAuthMock, apiMocks } = vi.hoisted(() => ({
  useAuthMock: vi.fn(() => ({
    accessToken: 'tok',
    user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
  })),
  apiMocks: {
    getEntityDetail: vi.fn(),
    exportUserData: vi.fn(),
    deleteAllUserData: vi.fn(),
  },
}));

vi.mock('@/auth', () => ({ useAuth: () => useAuthMock() }));

vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return { ...actual, knowledgeApi: apiMocks };
});

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

// Import AFTER mocks so the components pick them up.
import { EntitiesTable } from '../EntitiesTable';
import { EntityDetailPanel } from '../EntityDetailPanel';
import { PrivacyTab } from '../PrivacyTab';

function makeEntity(overrides: Partial<Entity> = {}): Entity {
  return {
    id: 'ent-1',
    user_id: 'u1',
    project_id: null,
    name: 'Kai',
    canonical_name: 'kai',
    kind: 'character',
    aliases: [],
    canonical_version: 1,
    source_types: ['chat_turn'],
    confidence: 0.9,
    archived_at: null,
    archive_reason: null,
    evidence_count: 3,
    mention_count: 5,
    created_at: null,
    updated_at: '2026-04-20T00:00:00Z',
    ...overrides,
  };
}

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

// ── EntitiesTable ──────────────────────────────────────────────────

describe('EntitiesTable (C5 mobile polish)', () => {
  it('renders BOTH desktop (hidden md:block) and mobile (md:hidden) trees', () => {
    render(
      <EntitiesTable
        entities={[makeEntity()]}
        selectedEntityId={null}
        onSelect={vi.fn()}
      />,
    );
    const desktop = screen.getByTestId('entities-table-desktop');
    const mobile = screen.getByTestId('entities-table-mobile');
    // Desktop container: responsive show class pair.
    expect(desktop.className).toContain('hidden');
    expect(desktop.className).toContain('md:block');
    // Mobile container: inverse pair.
    expect(mobile.className).toContain('md:hidden');
  });

  it('mobile tree renders card-per-row with native button semantics + aria-label', () => {
    const onSelect = vi.fn();
    render(
      <EntitiesTable
        entities={[makeEntity({ id: 'ent-1', name: 'Kai' })]}
        selectedEntityId={null}
        onSelect={onSelect}
      />,
    );
    const mobileRows = screen.getAllByTestId('entities-row-mobile');
    expect(mobileRows).toHaveLength(1);
    expect(mobileRows[0].getAttribute('data-entity-id')).toBe('ent-1');
    // /review-impl LOW2: mobile cards drop role="row" — no
    // columnheader context on mobile means the role was semantic
    // drift. Native <button> semantics suffice; aria-label
    // carries the entity name for SR announcement.
    expect(mobileRows[0].getAttribute('role')).toBeNull();
    expect(mobileRows[0].tagName).toBe('BUTTON');
    expect(mobileRows[0].getAttribute('aria-label')).toBe('Kai');
    // Contains the entity name visually.
    expect(mobileRows[0].textContent).toContain('Kai');
  });

  it('selected state is carried through BOTH trees', () => {
    render(
      <EntitiesTable
        entities={[makeEntity({ id: 'ent-sel' })]}
        selectedEntityId="ent-sel"
        onSelect={vi.fn()}
      />,
    );
    const desktopRow = screen.getAllByTestId('entities-row')[0];
    const mobileRow = screen.getAllByTestId('entities-row-mobile')[0];
    // bg-primary/5 ring-1 ring-primary/30 — the selected visual cue
    // must reach BOTH trees so a user whose viewport crosses the md
    // boundary mid-selection doesn't lose the visual anchor.
    expect(desktopRow.className).toContain('bg-primary/5');
    expect(mobileRow.className).toContain('bg-primary/5');
  });
});

// ── EntityDetailPanel ──────────────────────────────────────────────

describe('EntityDetailPanel (C5 mobile polish)', () => {
  const ENTITY_FIXTURE = {
    id: 'ent-1',
    user_id: 'u1',
    project_id: null,
    name: 'Kai',
    canonical_name: 'kai',
    kind: 'character',
    aliases: [],
    canonical_version: 1,
    source_types: ['chat_turn'],
    confidence: 0.9,
    archived_at: null,
    archive_reason: null,
    evidence_count: 0,
    mention_count: 0,
    created_at: null,
    updated_at: null,
    relations: [],
    relations_truncated: false,
  };

  it('Dialog.Content has md:max-w-md (not bare max-w-md) so mobile gets full width', () => {
    apiMocks.getEntityDetail.mockResolvedValue(ENTITY_FIXTURE);
    const Wrapper = wrapper();
    render(
      <Wrapper>
        <EntityDetailPanel open={true} onOpenChange={vi.fn()} entityId="ent-1" />
      </Wrapper>,
    );
    const panel = screen.getByTestId('entity-detail-panel');
    expect(panel.className).toContain('md:max-w-md');
    // Assert the bare max-w-md constraint is GONE — the whole point
    // of this cycle's change is that mobile gets the full viewport.
    // classList.contains catches exactly 'max-w-md' vs 'md:max-w-md'.
    expect(panel.classList.contains('max-w-md')).toBe(false);
    // And w-full is still present so mobile fills.
    expect(panel.className).toContain('w-full');
  });

  it('/review-impl HIGH: X close button carries TOUCH_TARGET_SQUARE_MOBILE_ONLY_CLASS', () => {
    // Full-width mobile panel blocks overlay-dismiss; the X button
    // is the sole dismiss path. 24×24px wouldn't cut it for fat
    // thumbs on 375px phones. Lock the 44×44 floor.
    apiMocks.getEntityDetail.mockResolvedValue(ENTITY_FIXTURE);
    const Wrapper = wrapper();
    render(
      <Wrapper>
        <EntityDetailPanel open={true} onOpenChange={vi.fn()} entityId="ent-1" />
      </Wrapper>,
    );
    const closeBtn = screen.getByTestId('entity-detail-close');
    expect(closeBtn.className).toContain('min-h-[44px]');
    expect(closeBtn.className).toContain('min-w-[44px]');
    // Desktop release valves — both axes.
    expect(closeBtn.className).toContain('md:min-h-0');
    expect(closeBtn.className).toContain('md:min-w-0');
    // Icon re-centers via inline-flex now that the box expands.
    expect(closeBtn.className).toContain('inline-flex');
    expect(closeBtn.className).toContain('items-center');
    expect(closeBtn.className).toContain('justify-center');
  });
});

// ── PrivacyTab ─────────────────────────────────────────────────────

describe('PrivacyTab (C5 mobile polish)', () => {
  it('Export button has TOUCH_TARGET_MOBILE_ONLY_CLASS applied', () => {
    const Wrapper = wrapper();
    render(
      <Wrapper>
        <PrivacyTab />
      </Wrapper>,
    );
    // Export button = first button in the component (Download icon).
    const exportBtn = screen.getByRole('button', { name: /export/i });
    expect(exportBtn.className).toContain('min-h-[44px]');
    expect(exportBtn.className).toContain('md:min-h-0');
  });

  it('Delete button has TOUCH_TARGET_MOBILE_ONLY_CLASS applied', () => {
    const Wrapper = wrapper();
    render(
      <Wrapper>
        <PrivacyTab />
      </Wrapper>,
    );
    // Only one Delete button renders BEFORE the dialog is opened.
    const deleteBtn = screen.getByRole('button', { name: /delete/i });
    expect(deleteBtn.className).toContain('min-h-[44px]');
    expect(deleteBtn.className).toContain('md:min-h-0');
  });

  it('Dialog cancel + confirm buttons carry TOUCH_TARGET_MOBILE_ONLY_CLASS when dialog opens', () => {
    const Wrapper = wrapper();
    render(
      <Wrapper>
        <PrivacyTab />
      </Wrapper>,
    );
    // Open the dialog.
    fireEvent.click(screen.getByRole('button', { name: /delete/i }));
    // /review-impl C5: scope to the dialog subtree via `within()`
    // instead of grabbing the last of an ambiguous cross-DOM match.
    // Radix Portal mounts the dialog at document.body — `getByRole`
    // still finds it, but scoping via the dialog role makes the
    // query explicit + robust if someone else ever adds a Delete
    // button elsewhere in the rendered tree.
    const dialog = screen.getByRole('dialog');
    const cancelBtn = within(dialog).getByRole('button', { name: /cancel/i });
    expect(cancelBtn.className).toContain('min-h-[44px]');
    expect(cancelBtn.className).toContain('md:min-h-0');
    const confirmBtn = within(dialog).getByRole('button', { name: /delete/i });
    expect(confirmBtn.className).toContain('min-h-[44px]');
    expect(confirmBtn.className).toContain('md:min-h-0');
  });

  it('/review-impl LOW3: Export + Delete buttons retain TOUCH_TARGET when disabled (no accessToken)', () => {
    // Regression guard: a change like
    // `className={cn(base, !disabled && TOUCH_TARGET_...)}` would
    // pass the default-enabled tests but silently break mobile UX
    // when the user isn't authenticated. Forcing the disabled
    // branch here locks the "always-applied" contract.
    useAuthMock.mockReturnValueOnce({
      accessToken: null,
      user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
    });
    const Wrapper = wrapper();
    render(
      <Wrapper>
        <PrivacyTab />
      </Wrapper>,
    );
    const exportBtn = screen.getByRole('button', { name: /export/i });
    expect(exportBtn).toBeDisabled();
    expect(exportBtn.className).toContain('min-h-[44px]');
    expect(exportBtn.className).toContain('md:min-h-0');

    const deleteBtn = screen.getByRole('button', { name: /delete/i });
    expect(deleteBtn).toBeDisabled();
    expect(deleteBtn.className).toContain('min-h-[44px]');
    expect(deleteBtn.className).toContain('md:min-h-0');
  });
});
