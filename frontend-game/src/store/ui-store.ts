// UI state: which modal is open, sidebar collapsed/expanded, etc.
// Per-device, NOT synced (spec data-persistence rule for per-device UI prefs).

import { create } from 'zustand';

export type ModalKind = null | 'settings' | 'inventory' | 'dialog' | 'confirm';

export interface UiState {
  modal: ModalKind;
  sidebarCollapsed: boolean;
  openModal: (m: Exclude<ModalKind, null>) => void;
  closeModal: () => void;
  toggleSidebar: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  modal: null,
  sidebarCollapsed: false,
  openModal: (m) => set({ modal: m }),
  closeModal: () => set({ modal: null }),
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
}));
