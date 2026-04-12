import { useEffect, useRef } from 'react';

/**
 * Global keyboard shortcuts for the chat page.
 * Uses refs so the event listener is registered once — no detach/reattach on every render.
 * - Ctrl+N: open new chat dialog
 * - Escape: stop streaming (only when onStopStreaming is non-null)
 */
export function useKeyboardShortcuts(
  onNewChat: () => void,
  onStopStreaming: (() => void) | null,
) {
  const newChatRef = useRef(onNewChat);
  const stopRef = useRef(onStopStreaming);
  newChatRef.current = onNewChat;
  stopRef.current = onStopStreaming;

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.ctrlKey && e.key === 'n') {
        e.preventDefault();
        newChatRef.current();
      }
      if (e.key === 'Escape' && stopRef.current) {
        stopRef.current();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);
}
