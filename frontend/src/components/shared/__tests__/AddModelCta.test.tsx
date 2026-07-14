import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { AddModelCta } from '../AddModelCta';
import { StudioHostProvider, useStudioHost, type StudioHost } from '@/features/studio/host/StudioHostProvider';

// C0 — AddModelCta deep-links to the registration surface AND carries a return
// path so the user round-trips back. The adversary case: a one-way link that
// drops the return leaves the user stranded after registering.
//
// X-1 / DOCK-7 — the SECOND adversary case, and the reason this component is shared: inside a
// studio dock panel a bare <Link> NAVIGATES THE SPA AWAY FROM THE STUDIO and unmounts the entire
// dockview layout — the user loses their whole workspace to click "Add a model". Every ModelPicker
// empty state renders this CTA, so the fix lives HERE, once, and ~8 call sites inherit it.

function hrefOf() {
  return screen.getByRole('link').getAttribute('href') ?? '';
}

/** Renders the router's current path, so a test can prove the SPA did NOT navigate. */
function LocationProbe() {
  const loc = useLocation();
  return <span data-testid="loc">{`${loc.pathname}${loc.search}`}</span>;
}

/** Grabs the live host so the test can inject a fake dockview api (_dockApiRef) — the same
 *  injection StudioHostProvider.test.tsx uses. This drives the REAL chain
 *  (followStudioLink → resolveStudioLink → SETTINGS_RE → host.openPanel → api.addPanel)
 *  rather than mocking useOptionalStudioHost, which would only assert our own mock. */
function captureHost(sink: { host: StudioHost | null }) {
  return function Capture() {
    sink.host = useStudioHost();
    return null;
  };
}

describe('AddModelCta (C0)', () => {
  it('deep-links to /settings/providers carrying an explicit returnTo', () => {
    render(
      <MemoryRouter>
        <AddModelCta returnTo="/knowledge/projects/abc/build" capability="embedding" />
      </MemoryRouter>,
    );
    const href = hrefOf();
    expect(href).toContain('/settings/providers');
    expect(href).toContain(`return=${encodeURIComponent('/knowledge/projects/abc/build')}`);
  });

  it('defaults returnTo to the current location (path + query) when not given', () => {
    render(
      <MemoryRouter initialEntries={['/compose?work=42']}>
        <AddModelCta />
      </MemoryRouter>,
    );
    expect(hrefOf()).toContain(`return=${encodeURIComponent('/compose?work=42')}`);
  });

  it('renders the capability in the default label', () => {
    render(
      <MemoryRouter>
        <AddModelCta capability="chat" />
      </MemoryRouter>,
    );
    expect(screen.getByRole('link')).toHaveTextContent('Add a chat model');
  });
});

describe('AddModelCta — DOCK-7 (X-1)', () => {
  function renderInStudio(props: Parameters<typeof AddModelCta>[0] = {}) {
    const sink: { host: StudioHost | null } = { host: null };
    const Capture = captureHost(sink);
    const addPanel = vi.fn();
    render(
      <MemoryRouter initialEntries={['/books/b1/studio']}>
        <StudioHostProvider bookId="b1">
          <Capture />
          <LocationProbe />
          <AddModelCta {...props} />
        </StudioHostProvider>
      </MemoryRouter>,
    );
    // The dock api arrives after DockviewReact.onReady in prod; inject a fake so openPanel's
    // `if (!api) return` guard doesn't swallow the call.
    sink.host!._dockApiRef.current = { getPanel: () => null, addPanel } as never;
    return { addPanel };
  }

  // The anchor IS the bug: a preventDefault-ed <Link> still renders an <a href> that a middle-click
  // or ⌘-click navigates anyway — tearing the dock down by the exact path this fix exists to close.
  it('inside the studio it renders a BUTTON, not a link', () => {
    renderInStudio({ capability: 'chat' });
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByRole('button')).toHaveTextContent('Add a chat model');
  });

  it('clicking it OPENS the settings panel on Providers and does NOT navigate', () => {
    const { addPanel } = renderInStudio();
    fireEvent.click(screen.getByRole('button'));

    // Verify by EFFECT: the panel actually opened on the providers tab (SettingsPanel reads
    // params.tab; 'providers' is a valid SettingsTabId) — not merely that a button rendered.
    expect(addPanel).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'settings', params: { tab: 'providers' } }),
    );
    // …and the SPA never left the studio route, so the dockview layout is still mounted.
    expect(screen.getByTestId('loc')).toHaveTextContent('/books/b1/studio');
  });

  it('preserves the link variant as a button (styling variants both branch)', () => {
    renderInStudio({ variant: 'link', capability: 'embedding' });
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByRole('button')).toHaveTextContent('Add a embedding model');
  });
});
