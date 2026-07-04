import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// react-i18next is globally mocked in vitest.setup.ts to return the KEY itself (repo
// convention — assert on keys, not English fallback text; no need to re-mock here).
const hostMocks = vi.hoisted(() => ({ openPanel: vi.fn(), useRegisterStudioTool: vi.fn() }));
vi.mock('../../host/StudioHostProvider', () => ({
  useStudioHost: () => ({ openPanel: hostMocks.openPanel }),
  useRegisterStudioTool: hostMocks.useRegisterStudioTool,
}));

import { UserGuidePanel } from '../UserGuidePanel';
import { OPENABLE_STUDIO_PANELS } from '../catalog';

const fakeProps = () => ({ api: { setTitle: vi.fn() } }) as never;

describe('UserGuidePanel', () => {
  it('renders a group section for every category present in the real catalog', () => {
    render(<UserGuidePanel {...fakeProps()} />);
    const categories = new Set(OPENABLE_STUDIO_PANELS.map((p) => p.category ?? 'platform'));
    for (const category of categories) {
      expect(screen.getByTestId(`studio-user-guide-group-${category}`)).toBeInTheDocument();
    }
  });

  it('renders an Open row for every openable panel (catalog-driven, no hand-authored list)', () => {
    render(<UserGuidePanel {...fakeProps()} />);
    for (const p of OPENABLE_STUDIO_PANELS) {
      expect(screen.getByTestId(`studio-user-guide-open-${p.id}`)).toBeInTheDocument();
    }
  });

  it('clicking an Open row calls host.openPanel with that panel id', () => {
    render(<UserGuidePanel {...fakeProps()} />);
    fireEvent.click(screen.getByTestId('studio-user-guide-open-compose'));
    expect(hostMocks.openPanel).toHaveBeenCalledWith('compose', expect.objectContaining({ title: expect.any(String) }));
  });

  // #19 — falls back to descKey when a panel has no dedicated guideBodyKey yet (Wave 1 state).
  it('falls back to descKey for a panel with no guideBodyKey', () => {
    render(<UserGuidePanel {...fakeProps()} />);
    const composeDef = OPENABLE_STUDIO_PANELS.find((p) => p.id === 'compose')!;
    expect(composeDef.guideBodyKey).toBeUndefined();
    expect(screen.getByTestId('studio-user-guide-open-compose')).toHaveTextContent(composeDef.descKey);
  });
});
