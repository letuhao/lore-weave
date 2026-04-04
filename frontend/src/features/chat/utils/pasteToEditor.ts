/**
 * Custom event for pasting chat output content into the Chapter Editor.
 * Decoupled from both chat and editor — uses DOM CustomEvent.
 */

export const PASTE_TO_EDITOR_EVENT = 'loreweave:paste-to-editor';

export interface PasteToEditorDetail {
  text: string;
  language?: string | null;
  sourceOutputId?: string;
}

export function firePasteToEditor(detail: PasteToEditorDetail) {
  window.dispatchEvent(
    new CustomEvent(PASTE_TO_EDITOR_EVENT, { detail }),
  );
}

export function onPasteToEditor(handler: (detail: PasteToEditorDetail) => void) {
  const listener = (e: Event) => {
    handler((e as CustomEvent<PasteToEditorDetail>).detail);
  };
  window.addEventListener(PASTE_TO_EDITOR_EVENT, listener);
  return () => window.removeEventListener(PASTE_TO_EDITOR_EVENT, listener);
}
