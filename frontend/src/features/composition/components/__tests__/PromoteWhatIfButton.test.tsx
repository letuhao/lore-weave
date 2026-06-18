import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PromoteWhatIfButton } from '../PromoteWhatIfButton';
import type { WhatIfDraft } from '../../hooks/useWhatIfPromotion';
import type { Work } from '../../types';

// i18n: render the default value so labels resolve in tests.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? _k }),
}));

const promoteMock = vi.fn();
const hookState = vi.hoisted(() => ({
  buildDeriveBody: vi.fn(),
  promote: () => promoteMock(),
  isPromoting: false,
  error: null as string | null,
  canPromote: true,
}));
vi.mock('../../hooks/useWhatIfPromotion', () => ({
  useWhatIfPromotion: () => hookState,
}));

const sourceWork: Work = {
  project_id: 'src-proj', user_id: 'u1', book_id: 'book-1',
  active_template_id: null, status: 'active', settings: {}, version: 1,
};
const draft: WhatIfDraft = {
  branchPoint: null, taxonomy: 'au', povAnchor: null, canonRules: [], overrides: {}, name: 'WI',
};

beforeEach(() => {
  promoteMock.mockClear();
  hookState.isPromoting = false;
  hookState.error = null;
  hookState.canPromote = true;
});

describe('PromoteWhatIfButton (C27)', () => {
  it('renders the ephemeral what-if badge + promote action and fires promote() on click', () => {
    render(<PromoteWhatIfButton sourceWork={sourceWork} draft={draft} token="tok" />);
    expect(screen.getByTestId('promote-whatif-ephemeral-badge')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('promote-whatif-action'));
    expect(promoteMock).toHaveBeenCalledTimes(1);
  });

  it('disables the action while promoting', () => {
    hookState.isPromoting = true;
    render(<PromoteWhatIfButton sourceWork={sourceWork} draft={draft} token="tok" />);
    expect(screen.getByTestId('promote-whatif-action')).toBeDisabled();
  });

  it('disables the action when there is no token', () => {
    render(<PromoteWhatIfButton sourceWork={sourceWork} draft={draft} token={null} />);
    expect(screen.getByTestId('promote-whatif-action')).toBeDisabled();
  });

  it('shows the error when promotion fails', () => {
    hookState.error = 'promotion reused the source project_id';
    render(<PromoteWhatIfButton sourceWork={sourceWork} draft={draft} token="tok" />);
    expect(screen.getByTestId('promote-whatif-error')).toHaveTextContent(/reused the source project/i);
  });
});
