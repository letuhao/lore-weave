// T21 — the Motif Library must say what it is NOT.
//
// A 2026-09-06 human-sim run opened this panel expecting a tracker for its story's own recurring
// imagery -- the book's steering rules name two such motifs explicitly -- and found a picker of
// generic cross-genre plot templates. It recorded the capability as missing. The existing copy was
// accurate and still misread, because the panel is called "Motif Library" and "motif" means
// something else to an author.
//
// Renaming the feature is a product decision with an 18-language ripple. Saying what it is not
// costs nothing and answers the question at the moment it is asked.
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));

import { MotifEmptyState } from '../MotifEmptyState';

const render_ = () =>
  render(<MotifEmptyState onNewMotif={() => {}} onBrowseSystem={() => {}} />);

describe('MotifEmptyState (T21)', () => {
  it('states that it does NOT track a story own recurring themes', () => {
    render_();
    const el = screen.getByTestId('motif-empty-not-themes');
    expect(el.textContent).toMatch(/not a tracker/i);
    expect(el.textContent).toMatch(/your own story/i);
  });

  it('still explains what it IS — the disclaimer must not replace the purpose', () => {
    render_();
    expect(screen.getByTestId('motif-empty').textContent).toMatch(/plot shapes/i);
  });
});
