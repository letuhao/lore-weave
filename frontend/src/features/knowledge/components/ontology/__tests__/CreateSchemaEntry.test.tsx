import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { CreateSchemaEntry } from '../CreateSchemaEntry';

// 14_kg_panels.md K9 (DOCK-7) — CreateSchemaEntry's "Adopt a template" CTA used to
// be a hard <Link> to the legacy /books/:bookId/kg-ontology?view=adopt route. The
// new `onAdoptCta` callback lets the `kg-schema` studio panel switch its own
// internal tab instead (no route hop, no Router needed). The legacy
// ProjectDetailShell call site (no onAdoptCta) must keep working unchanged.

describe('CreateSchemaEntry — adopt CTA (DOCK-7 fix)', () => {
  it('calls onAdoptCta (no <Link>, no Router required) when provided', () => {
    const onAdoptCta = vi.fn();
    // Deliberately NOT wrapped in a Router — a real <Link> would throw here.
    render(
      <CreateSchemaEntry
        bookId="b-1"
        templates={[]}
        createBlank={vi.fn()}
        clone={vi.fn()}
        onAdoptCta={onAdoptCta}
      />,
    );
    fireEvent.click(screen.getByTestId('adopt-template-cta'));
    expect(onAdoptCta).toHaveBeenCalledTimes(1);
  });

  it('falls back to the legacy <Link> when onAdoptCta is omitted (ProjectDetailShell call site)', () => {
    render(
      <MemoryRouter>
        <CreateSchemaEntry bookId="b-1" templates={[]} createBlank={vi.fn()} clone={vi.fn()} />
      </MemoryRouter>,
    );
    const cta = screen.getByTestId('adopt-template-cta');
    expect(cta.tagName).toBe('A');
    expect(cta).toHaveAttribute('href', '/books/b-1/kg-ontology?view=adopt');
  });

  it('shows the bookless hint when there is no bookId and no onAdoptCta', () => {
    render(
      <MemoryRouter>
        <CreateSchemaEntry bookId={null} templates={[]} createBlank={vi.fn()} clone={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId('adopt-template-cta')).not.toBeInTheDocument();
  });
});
