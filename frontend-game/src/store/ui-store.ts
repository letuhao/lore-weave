// UI state: which modal is open, etc.
// Per-device, NOT synced (spec data-persistence rule for per-device UI prefs).

import { create } from 'zustand';

export type ModalKind = null | 'settings' | 'inventory' | 'dialog' | 'confirm';

export interface UiState {
  modal: ModalKind;
  openModal: (m: Exclude<ModalKind, null>) => void;
  closeModal: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  modal: null,
  openModal: (m) => set({ modal: m }),
  closeModal: () => set({ modal: null }),
}));
