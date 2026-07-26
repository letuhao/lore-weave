import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Verify-by-EFFECT for the deep-link: the chat header opens
// /context-inspector?session=<id>, and the page must forward that id to the view
// as initialSessionId (so the inspector opens focused on THAT conversation). We
// spy on the data hook to capture the initialSessionId it actually receives.

const seen: { initialSessionId?: string | null } = {};
vi.mock('../useContextTrace', () => ({
  useContextTrace: (_enabled: boolean, initialSessionId?: string | null) => {
    seen.initialSessionId = initialSessionId;
    return {
      sessions: [],
      sessionId: initialSessionId ?? null,
      selectSession: vi.fn(),
      points: [],
      loading: false,
      error: null,
      reload: vi.fn(),
    };
  },
}));

import { ContextInspectorPage } from '../ContextInspectorPage';

describe('ContextInspectorPage — ?session= deep link', () => {
  it('forwards the ?session query param to the view as initialSessionId', () => {
    render(
      <MemoryRouter initialEntries={['/context-inspector?session=abc-123']}>
        <ContextInspectorPage />
      </MemoryRouter>,
    );
    expect(seen.initialSessionId).toBe('abc-123');
  });

  it('passes null when no ?session param is present (falls back to most-recent)', () => {
    seen.initialSessionId = undefined;
    render(
      <MemoryRouter initialEntries={['/context-inspector']}>
        <ContextInspectorPage />
      </MemoryRouter>,
    );
    expect(seen.initialSessionId).toBeNull();
  });
});
