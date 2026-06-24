import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

// C1 (BL-1) — the model register form must offer `rerank` as a first-class
// capability so a user can hand-tag a model rerank-capable. Toggling it must
// round-trip to `capability_flags.rerank=true` (AddModelModal collects the
// CapabilityFlags state verbatim into capability_flags). The capability token
// MUST be the canonical RERANK_CAPABILITY — never a divergent literal — so the
// RerankModelPicker (which filters on the same token) finds the model.

import { CapabilityFlags, KNOWN_FLAGS } from '../CapabilityFlags';
import { RERANK_CAPABILITY } from '../api';

describe('CapabilityFlags — rerank registration (C1, BL-1)', () => {
  it('includes rerank in KNOWN_FLAGS via the canonical RERANK_CAPABILITY token', () => {
    expect(RERANK_CAPABILITY).toBe('rerank');
    // Canonical token end-to-end: the register form offers exactly the value the
    // picker filters on. A divergent literal (e.g. 'reranker') would re-open the
    // C0 drift where a registered rerank model rendered with no badge.
    expect(KNOWN_FLAGS).toContain(RERANK_CAPABILITY);
  });

  it('renders a rerank capability checkbox in the register form', () => {
    render(<CapabilityFlags flags={{}} onChange={vi.fn()} />);
    // i18n is key-mocked in tests → label renders the literal key.
    expect(screen.getByText(`capability.flag.${RERANK_CAPABILITY}`)).toBeInTheDocument();
  });

  it('toggling rerank round-trips to capability_flags.rerank=true', () => {
    const onChange = vi.fn();
    render(<CapabilityFlags flags={{}} onChange={onChange} />);
    const rerankLabel = screen.getByText(`capability.flag.${RERANK_CAPABILITY}`).closest('label')!;
    const checkbox = rerankLabel.querySelector('input[type="checkbox"]')!;
    fireEvent.click(checkbox);
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ [RERANK_CAPABILITY]: true }),
    );
  });

  it('does NOT offer web_search as a model capability (it is an External Service, not a model)', () => {
    // web_search is registered via ExternalServicesCard, not as a tickable model
    // capability. A checkbox here would re-introduce the "tag web_search on an
    // LLM" confusion this split removed.
    expect(KNOWN_FLAGS).not.toContain('web_search');
    render(<CapabilityFlags flags={{}} onChange={vi.fn()} />);
    expect(screen.queryByText('capability.flag.web_search')).not.toBeInTheDocument();
  });
});
