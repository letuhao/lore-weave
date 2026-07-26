import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// react-i18next is globally mocked in vitest.setup.ts to return the KEY itself (repo
// convention — assert on keys, not English fallback text; no need to re-mock here).
const hostMocks = vi.hoisted(() => ({ openPanel: vi.fn(), publish: vi.fn() }));
vi.mock('../../../host/StudioHostProvider', () => ({
  useStudioHost: () => ({ openPanel: hostMocks.openPanel, publish: hostMocks.publish }),
}));

const onboardingMocks = vi.hoisted(() => ({ role: null as string | null, isLoading: false }));
vi.mock('../../../onboarding/useStudioOnboarding', () => ({
  useStudioOnboarding: () => onboardingMocks,
}));

import { WelcomePanel } from '../WelcomePanel';
import { getStudioPanelDef } from '../../../panels/catalog';

const ROLE_HIGHLIGHTS: Record<string, string[]> = {
  writer: ['compose', 'editor', 'planner'],
  worldbuilder: ['glossary', 'wiki', 'knowledge'],
  translator: ['translation', 'enrichment-compose'],
  enricher: ['enrichment-gaps', 'enrichment-sources'],
  manager: ['sharing', 'book-settings'],
};

const fakeProps = () => ({}) as never;

describe('WelcomePanel', () => {
  it('every ROLE_HIGHLIGHTS id resolves to a real catalog entry (no silent drop on a catalog rename)', () => {
    for (const [role, ids] of Object.entries(ROLE_HIGHLIGHTS)) {
      for (const id of ids) {
        expect(getStudioPanelDef(id), `role "${role}" highlight "${id}" must exist in the catalog`).toBeTruthy();
      }
    }
  });

  it('renders no highlights while the role pref is still loading', () => {
    onboardingMocks.isLoading = true;
    onboardingMocks.role = null;
    render(<WelcomePanel {...fakeProps()} />);
    expect(screen.queryByTestId('welcome-highlights')).not.toBeInTheDocument();
  });

  it('renders the role-tailored highlight buttons once loaded, and opens a panel on click', () => {
    onboardingMocks.isLoading = false;
    onboardingMocks.role = 'worldbuilder';
    render(<WelcomePanel {...fakeProps()} />);

    for (const id of ROLE_HIGHLIGHTS.worldbuilder) {
      expect(screen.getByTestId(`welcome-highlight-${id}`)).toBeInTheDocument();
    }
    fireEvent.click(screen.getByTestId('welcome-highlight-glossary'));
    expect(hostMocks.openPanel).toHaveBeenCalledWith('glossary', expect.objectContaining({ title: expect.any(String) }));
  });

  it('falls back to the default highlights when role is unset (never crashes, never empty)', () => {
    onboardingMocks.isLoading = false;
    onboardingMocks.role = null;
    render(<WelcomePanel {...fakeProps()} />);
    expect(screen.getByTestId('welcome-highlight-compose')).toBeInTheDocument();
    expect(screen.getByTestId('welcome-highlight-editor')).toBeInTheDocument();
  });

  it('the Open User Guide button opens the user-guide panel', () => {
    onboardingMocks.isLoading = false;
    onboardingMocks.role = null;
    render(<WelcomePanel {...fakeProps()} />);
    fireEvent.click(screen.getByTestId('welcome-open-user-guide'));
    expect(hostMocks.openPanel).toHaveBeenCalledWith('user-guide', expect.objectContaining({ title: expect.any(String) }));
  });

  it('the Start Guided Tour button publishes a startGuidedTour bus event (crosses the DOCK-4 boundary via the bus, not a prop callback)', () => {
    onboardingMocks.isLoading = false;
    onboardingMocks.role = null;
    render(<WelcomePanel {...fakeProps()} />);
    fireEvent.click(screen.getByTestId('welcome-start-guided-tour'));
    expect(hostMocks.publish).toHaveBeenCalledWith({ type: 'startGuidedTour' });
  });
});
