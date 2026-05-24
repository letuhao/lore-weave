// Central TanStack Query key factory. All hooks reference these keys
// so cache invalidation is consistent and discoverable.

export const queryKeys = {
  health: {
    tilemap: () => ['health', 'tilemap'] as const,
  },
  tilemap: {
    render: (zoneId: string) => ['tilemap', 'render', zoneId] as const,
  },
  auth: {
    me: () => ['auth', 'me'] as const,
  },
};
