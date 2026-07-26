import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? _k, i18n: { language: 'en' } }),
}));
vi.mock('../useStudioPanel', () => ({ useStudioPanel: () => 'Search' }));

const host = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock('../../host/StudioHostProvider', () => ({ useStudioHost: () => host.value }));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const proj = vi.hoisted(() => ({ value: { projectId: 'p-1', isLoading: false } as { projectId: string | null; isLoading: boolean } }));
vi.mock('@/features/knowledge/hooks/useBookKnowledgeProject', () => ({
  useBookKnowledgeProject: () => proj.value,
}));

// Stub the two mode surfaces — this is a WIRING test (mode toggle + params → the right surface
// with the right props), not a re-test of RawSearchPanel / SemanticSearchList.
const rawProps = vi.hoisted(() => ({ value: null as unknown }));
vi.mock('@/features/raw-search/components/RawSearchPanel', () => ({
  RawSearchPanel: (p: unknown) => {
    rawProps.value = p;
    return <div data-testid="raw-search-stub" />;
  },
}));
vi.mock('../../search/SemanticSearchList', () => ({
  SemanticSearchList: () => <div data-testid="semantic-stub" />,
}));

import { SearchPanel } from '../SearchPanel';

// Capture the onDidParametersChange listener so a test can fire it (the "rail re-queries an
// already-open panel" path — updateParameters → onDidParametersChange → re-seed).
function makeApi(): { api: never; fire: (p: Record<string, unknown>) => void } {
  let listener: ((p: Record<string, unknown> | undefined) => void) | null = null;
  const api = {
    onDidParametersChange: (cb: (p: Record<string, unknown> | undefined) => void) => {
      listener = cb;
      return { dispose: vi.fn() };
    },
    setTitle: vi.fn(),
  };
  return { api: api as never, fire: (p) => listener?.(p) };
}

describe('SearchPanel (S-11)', () => {
  beforeEach(() => {
    host.value = { bookId: 'b-1', focusManuscriptUnit: vi.fn(), openPanel: vi.fn() };
    proj.value = { projectId: 'p-1', isLoading: false };
    rawProps.value = null;
  });

  it('defaults to TEXT mode (reused RawSearchPanel) seeded with the params query + a studio onJump', () => {
    render(<SearchPanel api={makeApi().api} params={{ query: 'the tower' }} containerApi={{} as never} />);
    expect(screen.getByTestId('raw-search-stub')).toBeInTheDocument();
    expect(screen.queryByTestId('semantic-stub')).not.toBeInTheDocument();
    const p = rawProps.value as { bookId: string; initialQuery: string; onJump: (id: string) => void };
    expect(p.bookId).toBe('b-1');
    expect(p.initialQuery).toBe('the tower');
    // onJump routes into the in-dock editor
    p.onJump('ch-3');
    expect(host.value.focusManuscriptUnit).toHaveBeenCalledWith('ch-3');
  });

  it('opens in SEMANTIC mode when the rail seeds params.mode', () => {
    render(<SearchPanel api={makeApi().api} params={{ query: 'x', mode: 'semantic' }} containerApi={{} as never} />);
    expect(screen.getByTestId('semantic-stub')).toBeInTheDocument();
    expect(screen.queryByTestId('raw-search-stub')).not.toBeInTheDocument();
  });

  it('the in-panel toggle switches modes', () => {
    render(<SearchPanel api={makeApi().api} params={{}} containerApi={{} as never} />);
    expect(screen.getByTestId('raw-search-stub')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('search-mode-semantic'));
    expect(screen.getByTestId('semantic-stub')).toBeInTheDocument();
  });

  it('re-seeds when the rail re-queries an ALREADY-OPEN panel (onDidParametersChange)', () => {
    const { api, fire } = makeApi();
    render(<SearchPanel api={api} params={{ query: 'first', mode: 'text' }} containerApi={{} as never} />);
    expect((rawProps.value as { initialQuery: string }).initialQuery).toBe('first');
    // the rail submits a new query + a mode switch while the panel is open
    act(() => fire({ query: 'second', mode: 'semantic' }));
    expect(screen.getByTestId('semantic-stub')).toBeInTheDocument();
    // switch back to text and confirm the NEW query seeded (proves the reactive path, not stale mount)
    fireEvent.click(screen.getByTestId('search-mode-text'));
    expect((rawProps.value as { initialQuery: string }).initialQuery).toBe('second');
  });
});
