// Zustand store for high-frequency game state — synced from server,
// owned by server. React reads via selectors; writes happen only when
// the server pushes a new snapshot. Per spec §1 #4 + §5.

import { create } from 'zustand';

export interface GameState {
  hp: number;
  maxHp: number;
  mp: number;
  maxMp: number;
  inventory: string[];
  setVitals: (hp: number, mp: number) => void;
}

export const useGameStore = create<GameState>((set) => ({
  hp: 100,
  maxHp: 100,
  mp: 50,
  maxMp: 50,
  inventory: [],
  setVitals: (hp, mp) => set({ hp, mp }),
}));
