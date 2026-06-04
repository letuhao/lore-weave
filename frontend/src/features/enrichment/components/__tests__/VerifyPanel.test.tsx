import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { VerifyPanel } from '../VerifyPanel';
import type { CanonVerify, VerifyFlag } from '../../types';

const F = (over: Partial<VerifyFlag> = {}): VerifyFlag => ({
  kind: 'contradiction',
  dimension: null,
  evidence: 'evidence text',
  severity: 'low',
  ...over,
});

const V = (over: Partial<CanonVerify> = {}): CanonVerify => ({
  passed: true,
  verify_degraded: false,
  flags: [],
  ...over,
});

describe('VerifyPanel', () => {
  it('renders verify.none when verify is undefined', () => {
    render(<VerifyPanel verify={undefined} />);
    expect(screen.getByText('verify.none')).toBeInTheDocument();
    expect(screen.queryByTestId('enrichment-verify')).toBeNull();
  });

  it('no flags and not degraded -> clean signal', () => {
    render(<VerifyPanel verify={V({ flags: [], verify_degraded: false })} />);
    const clean = screen.getByTestId('verify-clean');
    expect(clean).toBeInTheDocument();
    expect(clean).toHaveTextContent('verify.clean');
  });

  it('verify_degraded with no flags -> degraded note, no clean signal', () => {
    render(<VerifyPanel verify={V({ flags: [], verify_degraded: true })} />);
    expect(screen.queryByTestId('verify-clean')).toBeNull();
    expect(screen.getByText('verify.degraded')).toBeInTheDocument();
  });

  it('renders one FlagRow per flag with kind label key, evidence, and severity key', () => {
    const flags = [
      F({ kind: 'injection', evidence: 'prompt injection found', severity: 'high' }),
      F({ kind: 'regurgitation', evidence: 'verbatim copy', severity: 'medium' }),
    ];
    render(<VerifyPanel verify={V({ flags })} />);
    // kind label key
    expect(screen.getByText('verify.flag.injection')).toBeInTheDocument();
    expect(screen.getByText('verify.flag.regurgitation')).toBeInTheDocument();
    // evidence rendered raw
    expect(screen.getByText('prompt injection found')).toBeInTheDocument();
    expect(screen.getByText('verbatim copy')).toBeInTheDocument();
    // severity key
    expect(screen.getByText('verify.severity.high')).toBeInTheDocument();
    expect(screen.getByText('verify.severity.medium')).toBeInTheDocument();
    // when flags present, the clean signal is hidden
    expect(screen.queryByTestId('verify-clean')).toBeNull();
  });

  it('high severity flag uses destructive styling', () => {
    render(<VerifyPanel verify={V({ flags: [F({ kind: 'anachronism', severity: 'high' })] })} />);
    const sev = screen.getByText('verify.severity.high');
    // severity tag carries the destructive class on high
    expect(sev.className).toContain('text-destructive');
    // the FlagRow container (the bordered card) also uses destructive border on high
    const card = sev.closest('div.rounded-md');
    expect(card?.className).toContain('border-destructive/30');
  });
});
