import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  TechniqueBadge,
  VerifyBadge,
  ReviewStatusBadge,
  H0Marker,
} from '../badges';

// react-i18next is mocked globally (vitest.setup.ts): t(key, opts) returns the
// dotted KEY verbatim (no {{x}} token in a dotted key), ignoring defaultValue.
// So every label asserted here is the i18n KEY, never English.

describe('TechniqueBadge', () => {
  it('fabrication -> P2 tier + technique.<t> label', () => {
    render(<TechniqueBadge technique="fabrication" />);
    const pill = screen.getByText('P2 · technique.fabrication');
    expect(pill).toBeInTheDocument();
    expect(pill).toHaveAttribute('title', 'technique.fabrication');
  });

  it('recook -> P3 tier + technique.<t> label', () => {
    render(<TechniqueBadge technique="recook" />);
    const pill = screen.getByText('P3 · technique.recook');
    expect(pill).toBeInTheDocument();
    expect(pill).toHaveAttribute('title', 'technique.recook');
  });

  it('retrieval (and any other technique) -> P1 tier', () => {
    render(<TechniqueBadge technique="retrieval" />);
    expect(screen.getByText('P1 · technique.retrieval')).toBeInTheDocument();
  });

  it('template -> P1 tier (else branch)', () => {
    render(<TechniqueBadge technique="template" />);
    expect(screen.getByText('P1 · technique.template')).toBeInTheDocument();
  });
});

describe('VerifyBadge', () => {
  it('renders nothing when status is undefined', () => {
    const { container } = render(<VerifyBadge />);
    expect(container.firstChild).toBeNull();
  });

  it('renders the verify.status.<s> key when a status is given', () => {
    render(<VerifyBadge status="verified_clean" />);
    expect(screen.getByText('verify.status.verified_clean')).toBeInTheDocument();
  });

  it('renders an unknown status verbatim (fallback class branch)', () => {
    render(<VerifyBadge status="quarantined" />);
    expect(screen.getByText('verify.status.quarantined')).toBeInTheDocument();
  });
});

describe('ReviewStatusBadge', () => {
  it('renders the review.<s> key', () => {
    render(<ReviewStatusBadge status="promoted" />);
    expect(screen.getByText('review.promoted')).toBeInTheDocument();
  });

  it('renders an unmapped status verbatim (fallback class branch)', () => {
    render(<ReviewStatusBadge status="proposed" />);
    expect(screen.getByText('review.proposed')).toBeInTheDocument();
  });
});

describe('H0Marker', () => {
  it('renders the marker testid + h0.marker label + h0.tooltip title', () => {
    render(<H0Marker />);
    const marker = screen.getByTestId('enrichment-h0-marker');
    expect(marker).toBeInTheDocument();
    expect(marker).toHaveTextContent('h0.marker');
    expect(marker).toHaveAttribute('title', 'h0.tooltip');
  });
});
