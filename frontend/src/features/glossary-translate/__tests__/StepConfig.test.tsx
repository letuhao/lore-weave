// 13_glossary_panels.md A6 — DOCK-7 fix: the "no models, add one" empty-state link must not
// route-navigate the whole app away from a mounted studio. Outside the studio it's still a
// normal <Link> (the classic GlossaryTab page has no StudioHost to route through).
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { StudioHostProvider } from '@/features/studio/host/StudioHostProvider';

vi.mock('@/components/model-picker', () => ({
  useUserModels: () => ({ models: [], loading: false }),
  ModelPicker: ({ emptyState }: { emptyState?: ReactNode }) => <div data-testid="model-picker">{emptyState}</div>,
}));
vi.mock('@/components/ai-task', () => ({ EffortSelect: () => <select data-testid="effort-select" /> }));

import { StepConfig } from '../StepConfig';

function baseProps() {
  return {
    targetLanguage: 'vi',
    overwriteMode: 'missing_only' as const,
    modelRef: '',
    effort: 'off' as const,
    sourceLanguage: 'en',
    onTargetLanguageChange: vi.fn(),
    onOverwriteModeChange: vi.fn(),
    onModelChange: vi.fn(),
    onModelNameChange: vi.fn(),
    onEffortChange: vi.fn(),
  };
}

describe('StepConfig empty-state link (DOCK-7)', () => {
  it('outside the studio, renders a normal <Link> to /settings/providers', () => {
    render(
      <MemoryRouter>
        <StepConfig {...baseProps()} />
      </MemoryRouter>,
    );
    const link = screen.getByText('config.addInSettings');
    expect(link.tagName).toBe('A');
    expect(link.getAttribute('href')).toBe('/settings/providers');
  });

  it('inside the studio, renders a button that opens the settings panel instead of navigating', () => {
    // openPanel is captured via the real StudioHostProvider — assert through its effect.
    render(
      <MemoryRouter>
        <StudioHostProvider bookId="b1">
          <StepConfig {...baseProps()} />
        </StudioHostProvider>
      </MemoryRouter>,
    );
    const trigger = screen.getByText('config.addInSettings');
    expect(trigger.tagName).toBe('BUTTON');
    // Clicking must not throw (openPanel is a no-op until a dock api attaches) and must not
    // be an <a> the browser would navigate — the tagName assertion above is the real proof;
    // this click just confirms the handler runs without crashing.
    expect(() => fireEvent.click(trigger)).not.toThrow();
  });
});
