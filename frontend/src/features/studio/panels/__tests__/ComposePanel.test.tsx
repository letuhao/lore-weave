import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useRegisteredTools } from '../../host/StudioHostProvider';

// The whole chat feature is embedded AS-IS; stub it here to capture the props the panel passes.
const chatProps = vi.hoisted(() => ({ value: null as Record<string, unknown> | null }));
vi.mock('@/features/chat/Chat', () => ({
  Chat: (p: Record<string, unknown>) => { chatProps.value = p; return <div data-testid="chat-stub" />; },
}));

import { ComposePanel } from '../ComposePanel';

const dockProps = {} as IDockviewPanelProps;

describe('ComposePanel', () => {
  it('embeds <Chat> with the host bookId + windowing (turn survives dock float/close)', () => {
    render(<StudioHostProvider bookId="book-42"><ComposePanel {...dockProps} /></StudioHostProvider>);
    expect(screen.getByTestId('chat-stub')).toBeTruthy();
    expect(chatProps.value).toMatchObject({ bookId: 'book-42', windowingEnabled: true });
  });

  it('registers itself as the "compose" studio tool (for the agent rack)', () => {
    let tools: ReturnType<typeof useRegisteredTools> = [];
    function Probe() { tools = useRegisteredTools(); return null; }
    render(
      <StudioHostProvider bookId="b1"><ComposePanel {...dockProps} /><Probe /></StudioHostProvider>,
    );
    const compose = tools.find((t) => t.panelId === 'compose');
    expect(compose).toBeTruthy();
    expect(compose?.commandId).toBe('studio.openPanel.compose');
    expect(compose?.mcpToolPrefixes).toContain('composition_');
  });
});
