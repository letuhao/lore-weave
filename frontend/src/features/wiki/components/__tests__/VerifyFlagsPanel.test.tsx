import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, o?: Record<string, unknown>) => (o?.defaultValue as string) ?? k,
  }),
}));

import { VerifyFlagsPanel } from '../VerifyFlagsPanel';
import type { WikiGenerationProvenance } from '../../types';

describe('VerifyFlagsPanel', () => {
  it('renders nothing with no flags and not blocked', () => {
    const { container } = render(<VerifyFlagsPanel provenance={null} blocked={false} />);
    expect(container.firstChild).toBeNull();
  });

  it('lists each verify flag with its evidence', () => {
    const provenance: WikiGenerationProvenance = {
      verify_flags: [
        { kind: 'anachronism', dimension: 'tech', evidence: 'mentions a phone', severity: 'high' },
        { kind: 'contradiction', dimension: 'canon', evidence: 'died in ch2', severity: 'medium' },
      ],
    };
    render(<VerifyFlagsPanel provenance={provenance} blocked={false} />);
    const items = screen.getAllByTestId('wiki-verify-flag');
    expect(items).toHaveLength(2);
    expect(screen.getByText(/mentions a phone/)).toBeTruthy();
    expect(screen.getByText(/died in ch2/)).toBeTruthy();
  });

  it('shows a blocked panel with a no-detail note when blocked but flagless', () => {
    render(<VerifyFlagsPanel provenance={{ verify_flags: [] }} blocked />);
    expect(screen.getByTestId('wiki-verify-flags')).toBeTruthy();
    expect(screen.getByText('gen.flags.blockedNoDetail')).toBeTruthy();
  });
});
