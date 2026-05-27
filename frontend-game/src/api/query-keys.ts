// Central TanStack Query key factory. All hooks reference these keys
// so cache invalidation is consistent and discoverable.

export const queryKeys = {
  health: {
    tilemap: () => ['health', 'tilemap'] as const,
  },
  tilemap: {
    render: (zoneId: string) => ['tilemap', 'render', zoneId] as const,
    zone: (params: { seed: number; gridWidth: number; gridHeight: number; tier: string }) =>
      ['tilemap', 'zone', params.tier, params.gridWidth, params.gridHeight, params.seed] as const,
  },
  auth: {
    me: () => ['auth', 'me'] as const,
  },
};
