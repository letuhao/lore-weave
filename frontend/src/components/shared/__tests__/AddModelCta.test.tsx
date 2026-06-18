import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AddModelCta } from '../AddModelCta';

// C0 — AddModelCta deep-links to the registration surface AND carries a return
// path so the user round-trips back. The adversary case: a one-way link that
// drops the return leaves the user stranded after registering.

function hrefOf() {
  return screen.getByRole('link').getAttribute('href') ?? '';
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
