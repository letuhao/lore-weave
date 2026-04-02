/**
 * Custom event for sending content from Chapter Editor to Chat.
 * Uses DOM CustomEvent — same decoupled pattern as paste-to-editor.
 */

export const SEND_TO_CHAT_EVENT = 'loreweave:send-to-chat';

export interface SendToChatDetail {
  /** Chapter title */
  chapterTitle: string;
  /** Text content (selected text or full draft) */
  text: string;
  /** Book ID for context */
  bookId: string;
  /** Chapter ID */
  chapterId: string;
}

export function fireSendToChat(detail: SendToChatDetail) {
  window.dispatchEvent(
    new CustomEvent(SEND_TO_CHAT_EVENT, { detail }),
  );
}

export function onSendToChat(handler: (detail: SendToChatDetail) => void) {
  const listener = (e: Event) => {
    handler((e as CustomEvent<SendToChatDetail>).detail);
  };
  window.addEventListener(SEND_TO_CHAT_EVENT, listener);
  return () => window.removeEventListener(SEND_TO_CHAT_EVENT, listener);
}
