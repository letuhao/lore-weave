// M2 — the platform home + activity feed types (mirrors the BFF HomeController shapes).

export type TileStatus = 'ok' | 'empty' | 'degraded';

export interface Tile<T> {
  status: TileStatus;
  data?: T;
  error?: string;
}

export interface HomeBook {
  id: string;
  title: string;
  updated_at?: string;
}
export interface HomeJob {
  id: string;
  kind?: string;
  status?: string;
  created_at?: string;
}

export interface HomeResponse {
  tiles: {
    activity: Tile<{ unread: number }>;
    books: Tile<HomeBook[]>;
    jobs: Tile<HomeJob[]>;
  };
  generated_at: string;
  /** Set when a critical source was down and the BFF served a cached snapshot. */
  stale?: boolean;
}

export interface ActivityItem {
  id: string;
  category: string;
  title: string;
  body?: string | null;
  read_at?: string | null;
  created_at: string;
  message_key?: string | null;
}

export interface ActivityFeedPage {
  items: ActivityItem[];
  /** Opaque keyset cursor for the next (older) page, or null at the end. */
  next_cursor: string | null;
  unread_count: number;
}
