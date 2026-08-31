// ChannelPanel — the minimal click-to-turn surface. Renders the roster from
// W1 + the outcome log, and submits actions through the channel client.
//
// ⚠ frontend-game (MMORPG client, :5176). Not frontend/ (:5174).
//
// MVC per CLAUDE.md: this component RENDERS. State lives in the zustand
// channel store; the network lives in the channel client. No fetch, no
// protocol knowledge, no business rules here.

import { useMemo, useState } from 'react';

import { createChannelClient } from '@/net/channel-client';
import { useChannelStore } from '@/store/channel-store';

export function ChannelPanel({ url, jwt }: { url: string; jwt: string }) {
  // One client per mounted panel; `useMemo` so a re-render never re-creates a
  // live socket (re-creating it on every render is the classic leak).
  const client = useMemo(() => createChannelClient(), []);
  const [joined, setJoined] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { roster, turnNumber, log, pending, selfEntityId, place } = useChannelStore();

  const join = async () => {
    try {
      await client.join(url, { jwt });
      setJoined(true);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const act = (tool: string, params: Record<string, unknown> = {}) => {
    client.submit({ vocabulary: 'combat_v1', tool, params });
  };

  if (!joined) {
    return (
      <div className="p-4">
        <button className="rounded bg-blue-600 px-3 py-1 text-white" onClick={() => void join()}>
          Join channel
        </button>
        {error && <p className="mt-2 text-red-500">{error}</p>}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      <header className="text-sm opacity-70">
        turn {turnNumber} · you are entity {selfEntityId ?? '—'}
        {/* `A4` — WHERE you are. Rendered only when the frame carries it: an
            actor that has never been sited is nowhere, and inventing a
            location would be the same confused claim as inventing a `self`.
            The place NAME when the node is a Domain, the level name otherwise
            -- `PF_001` gives only a Domain a place. */}
        {place && (
          <span data-testid="frame-place"> · at {place.place_name ?? place.level_name}</span>
        )}
        {/* The in-flight marker is a real UI state: acting twice while a turn
            is resolving is how a player double-spends a turn slot. */}
        {pending && <span className="ml-2 animate-pulse">· resolving…</span>}
      </header>

      <ul className="flex flex-col gap-1">
        {roster.map((r) => (
          <li key={r.entity_id} className="flex items-center gap-2">
            <span className="w-32">{r.display_name}</span>
            {/* REC-79: condition is its OWN field, never baked into the name. */}
            <span className="text-xs opacity-60">{r.condition}</span>
            {r.disposition === 'hostile' && (
              <button
                className="rounded border px-2 text-sm disabled:opacity-40"
                disabled={!!pending || r.condition === 'down'}
                onClick={() => act('strike', { target: `hostile-${r.entity_id}` })}
              >
                Strike
              </button>
            )}
          </li>
        ))}
      </ul>

      <div className="flex gap-2">
        <button
          className="rounded border px-2 text-sm disabled:opacity-40"
          disabled={!!pending}
          onClick={() => act('defend')}
        >
          Defend
        </button>
        <button
          className="rounded border px-2 text-sm disabled:opacity-40"
          disabled={!!pending}
          onClick={() => act('flee')}
        >
          Flee
        </button>
      </div>

      <ol className="max-h-48 overflow-y-auto text-sm">
        {log.map((line, i) => (
          <li key={`${i}-${line}`} className="opacity-80">
            {line}
          </li>
        ))}
      </ol>
    </div>
  );
}
