// Network state: connection status, latency, peer count. Used by
// status indicators in HUD and the reconnect UX in Session E.

import { create } from 'zustand';

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting';

export interface NetState {
  status: ConnectionStatus;
  latencyMs: number | null;
  peerCount: number;
  setStatus: (status: ConnectionStatus) => void;
  setLatency: (ms: number | null) => void;
  setPeerCount: (n: number) => void;
}

export const useNetStore = create<NetState>((set) => ({
  status: 'disconnected',
  latencyMs: null,
  peerCount: 0,
  setStatus: (status) => set({ status }),
  setLatency: (latencyMs) => set({ latencyMs }),
  setPeerCount: (peerCount) => set({ peerCount }),
}));
