// Part B — the opt-in "set up this book" shortcut. It must appear ONLY when the book lacks a plan
// (else the Work door alone suffices), and clicking it fires the create-both setup.
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SetupEverythingLink } from '../SetupEverythingLink';

const readiness = { hasWork: false, hasPlan: false, loading: false };
const setUp = vi.fn();
let busy = false;

vi.mock('../../hooks/useBookReadiness', () => ({ useBookReadiness: () => readiness }));
vi.mock('../../hooks/useBookSetup', () => ({ useBookSetup: () => ({ setUp, busy }) }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? _k }),
}));

afterEach(() => {
  readiness.hasPlan = false;
  readiness.loading = false;
  busy = false;
  setUp.mockReset();
});

describe('SetupEverythingLink (Part B)', () => {
  it('renders the shortcut and fires setUp when the book has no plan', () => {
    render(<SetupEverythingLink bookId="b1" token="tok" />);
    fireEvent.click(screen.getByTestId('book-setup-everything'));
    expect(setUp).toHaveBeenCalledTimes(1);
  });

  it('renders NOTHING once the book already has a plan (the Work door alone suffices)', () => {
    readiness.hasPlan = true;
    const { container } = render(<SetupEverythingLink bookId="b1" token="tok" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing while readiness is still loading (no premature shortcut)', () => {
    readiness.loading = true;
    const { container } = render(<SetupEverythingLink bookId="b1" token="tok" />);
    expect(container).toBeEmptyDOMElement();
  });
});
