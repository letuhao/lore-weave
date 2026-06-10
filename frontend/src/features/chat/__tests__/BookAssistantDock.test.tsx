import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

// Glossary-assistant P5 — the book-scoped assistant dock. The embedded <Chat> is
// stubbed; the behavior under test is the dock's mount/visibility lifecycle:
// lazy-mount on first open, then KEEP mounted (slid off-screen) on close so the
// chat state survives — CLAUDE.md: never conditionally unmount stateful components.

vi.mock('../Chat', () => ({ Chat: () => <div data-testid="chat-stub" /> }));

import { BookAssistantDock } from '../BookAssistantDock';

describe('BookAssistantDock', () => {
  it('does not mount the chat until first opened', () => {
    render(<BookAssistantDock bookId="b1" />);
    expect(screen.getByTestId('book-assistant-toggle')).toBeInTheDocument();
    expect(screen.queryByTestId('book-assistant-panel')).not.toBeInTheDocument();
    expect(screen.queryByTestId('chat-stub')).not.toBeInTheDocument();
  });

  it('mounts the chat on open', () => {
    render(<BookAssistantDock bookId="b1" />);
    fireEvent.click(screen.getByTestId('book-assistant-toggle'));
    const panel = screen.getByTestId('book-assistant-panel');
    expect(panel).toBeInTheDocument();
    expect(panel).toHaveAttribute('aria-hidden', 'false');
    expect(screen.getByTestId('chat-stub')).toBeInTheDocument();
  });

  it('keeps the chat mounted (only hidden) when closed', () => {
    render(<BookAssistantDock bookId="b1" />);
    fireEvent.click(screen.getByTestId('book-assistant-toggle'));
    fireEvent.click(screen.getByTestId('book-assistant-close'));
    // panel + chat are STILL in the DOM (mounted), just slid away + aria-hidden
    const panel = screen.getByTestId('book-assistant-panel');
    expect(panel).toBeInTheDocument();
    expect(panel).toHaveAttribute('aria-hidden', 'true');
    expect(screen.getByTestId('chat-stub')).toBeInTheDocument();
    // the floating toggle returns so the user can re-open
    expect(screen.getByTestId('book-assistant-toggle')).toBeInTheDocument();
  });
});
