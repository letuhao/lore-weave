import { useEffect, useRef, useState } from 'react';
import { createWsClient, type WsClient } from '@/net/ws-client';
import type { ServerToClient } from '@/net/protocol';
import { Button } from '@/components/shared/Button';
import { SERVICES } from '@/config/services';
import type { JSX } from 'react';

// EchoPanel — Session E V0 demo UI for verifying the WebSocket path
// end-to-end. Sends `echo` messages to game-server's EchoRoom and
// shows the response.
//
// Spec §16 Session E AC:
//  - Connect on mount (auth handshake)
//  - Type → send → see echo response
//  - Disconnect indicator when server stops
//  - Reconnect button when disconnected (uses stored token)
//
// Service URL + dev token now centralized in @/config/services (V0
// close-out cleanup) so V1 env-var injection lands in one place.

const GAME_SERVER_URL = SERVICES.gameServer;
const DEV_TOKEN = SERVICES.devToken;

type Status = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'error';

interface Entry {
  id: number;
  direction: 'out' | 'in' | 'system';
  text: string;
  ts: number;
}

export function EchoPanel(): JSX.Element {
  const [status, setStatus] = useState<Status>('idle');
  const [statusDetail, setStatusDetail] = useState<string>('');
  const [draft, setDraft] = useState('');
  const [entries, setEntries] = useState<Entry[]>([]);
  const clientRef = useRef<WsClient | null>(null);
  const nextId = useRef(0);

  const appendEntry = (direction: Entry['direction'], text: string): void => {
    setEntries((prev) => {
      const id = nextId.current++;
      const next = [...prev, { id, direction, text, ts: Date.now() }];
      return next.slice(-10); // keep last 10
    });
  };

  useEffect(() => {
    const client = createWsClient();
    clientRef.current = client;

    const offMessage = client.on((msg: ServerToClient) => {
      if (msg.kind === 'session-established') {
        setStatus('connected');
        setStatusDetail(msg.characterId);
        appendEntry('system', `connected as ${msg.characterId}`);
      } else if (msg.kind === 'world-event') {
        appendEntry('in', `${msg.eventId}: ${JSON.stringify(msg.payload)}`);
      } else if (msg.kind === 'action-result' && !msg.ok) {
        setStatus('disconnected');
        setStatusDetail(msg.reason ?? '');
        appendEntry('system', `error: ${msg.reason ?? 'unknown'}`);
      }
    });

    // Initial connect attempt.
    setStatus('connecting');
    client.connect(GAME_SERVER_URL, DEV_TOKEN).catch((err: Error) => {
      setStatus('error');
      setStatusDetail(err.message);
    });

    return () => {
      offMessage();
      client.disconnect();
      clientRef.current = null;
    };
  }, []);

  const onSend = (): void => {
    const text = draft.trim();
    if (!text || !clientRef.current) return;
    try {
      clientRef.current.send({ kind: 'echo', text });
      appendEntry('out', text);
      setDraft('');
    } catch (err) {
      appendEntry('system', `send failed: ${(err as Error).message}`);
    }
  };

  const onReconnect = async (): Promise<void> => {
    if (!clientRef.current) return;
    setStatus('connecting');
    try {
      await clientRef.current.reconnect();
    } catch {
      // Reconnect token expired — fall back to fresh connect.
      try {
        await clientRef.current.connect(GAME_SERVER_URL, DEV_TOKEN);
      } catch (err) {
        setStatus('error');
        setStatusDetail((err as Error).message);
      }
    }
  };

  const dotColor =
    status === 'connected'
      ? 'bg-emerald-400'
      : status === 'connecting'
        ? 'bg-amber-400'
        : status === 'disconnected' || status === 'error'
          ? 'bg-red-400'
          : 'bg-slate-500';

  return (
    <div className="absolute bottom-4 right-4 w-96 bg-slate-800/90 text-slate-100 p-3 rounded shadow-lg font-mono text-xs pointer-events-auto">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${dotColor}`} />
          <span className="font-bold">game-server: {status}</span>
        </div>
        {(status === 'disconnected' || status === 'error') && (
          <Button variant="secondary" onClick={onReconnect} className="text-xs px-2 py-1">
            Reconnect
          </Button>
        )}
      </div>
      {statusDetail && <div className="text-slate-400 mb-2 text-[10px]">{statusDetail}</div>}
      <div className="max-h-32 overflow-y-auto space-y-1 mb-2 bg-slate-900/50 p-2 rounded">
        {entries.length === 0 && <div className="text-slate-500 italic">no messages yet</div>}
        {entries.map((e) => (
          <div
            key={e.id}
            className={
              e.direction === 'out'
                ? 'text-sky-300'
                : e.direction === 'in'
                  ? 'text-emerald-300'
                  : 'text-slate-400 italic'
            }
          >
            <span className="text-slate-500">[{e.direction}]</span> {e.text}
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={draft}
          onChange={(ev) => setDraft(ev.target.value)}
          onKeyDown={(ev) => {
            if (ev.key === 'Enter') onSend();
          }}
          placeholder="type a message…"
          className="flex-1 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-100"
          disabled={status !== 'connected'}
        />
        <Button onClick={onSend} disabled={status !== 'connected'}>
          Send
        </Button>
      </div>
    </div>
  );
}
