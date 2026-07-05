import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// react-i18next is globally mocked in vitest.setup.ts to return the KEY itself (repo
// convention — assert on keys, not English fallback text; no need to re-mock here).
const hostMocks = vi.hoisted(() => ({ openPanel: vi.fn(), publish: vi.fn(), useRegisterStudioTool: vi.fn() }));
vi.mock('../../host/StudioHostProvider', () => ({
  useStudioHost: () => ({ openPanel: hostMocks.openPanel, publish: hostMocks.publish }),
  useRegisterStudioTool: hostMocks.useRegisterStudioTool,
}));

import { UserGuidePanel } from '../UserGuidePanel';
import { OPENABLE_STUDIO_PANELS } from '../catalog';
import { EDITOR_TOUR_CATALOG } from '../../onboarding/tours';

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

  // #19 Wave 2 — every non-hidden panel now has a dedicated guideBodyKey (richer than descKey);
  // the row renders it. (Wave 1 covered the guideBodyKey-absent fallback branch when no real
  // panel had one yet; that branch is still live in the component's `?? descKey` but every real
  // catalog entry now takes the guideBodyKey arm, so this test asserts the current, exercised path.)
  it('renders the dedicated guideBodyKey for a panel that has one (Wave 2 content)', () => {
    render(<UserGuidePanel {...fakeProps()} />);
    const composeDef = OPENABLE_STUDIO_PANELS.find((p) => p.id === 'compose')!;
    expect(composeDef.guideBodyKey).toBe('panels.compose.guideBody');
    expect(screen.getByTestId('studio-user-guide-open-compose')).toHaveTextContent(composeDef.guideBodyKey!);
  });

  // #19 Wave 3 — the editor deep-dive tours' only discoverable entry point (previously the
  // animated tour was reachable only via the Command Palette shortcut, no visible list).
  describe('tour picker (#19 Wave 3)', () => {
    it('renders a Start row for every tour in the catalog', () => {
      render(<UserGuidePanel {...fakeProps()} />);
      for (const tour of EDITOR_TOUR_CATALOG) {
        expect(screen.getByTestId(`studio-user-guide-tour-${tour.id}`)).toBeInTheDocument();
      }
    });

    it('clicking a tour row publishes startGuidedTour with that tourId', () => {
      render(<UserGuidePanel {...fakeProps()} />);
      fireEvent.click(screen.getByTestId('studio-user-guide-tour-editorMediaImage'));
      expect(hostMocks.publish).toHaveBeenCalledWith({ type: 'startGuidedTour', tourId: 'editorMediaImage' });
    });
  });
});
