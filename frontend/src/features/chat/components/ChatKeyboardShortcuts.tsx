import { useChatSession } from '../providers';
import { useChatStream } from '../providers';
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts';

/** Invisible component that wires global keyboard shortcuts to context. */
export function ChatKeyboardShortcuts() {
  const { setShowNewDialog } = useChatSession();
  const chat = useChatStream();

  useKeyboardShortcuts(
    () => setShowNewDialog(true),
    chat.isStreaming ? chat.stop : null,
  );

  return null;
}
