// P2·A2b — minimal structured logger for game-server.
//
// game-server is Colyseus + Express (NOT NestJS), so it has no framework Logger.
// This is the shared JSON-line logger (LG-1/LG-6): one `{ts, level, service, msg,
// ...fields}` line per call to stdout/stderr, so a log pipeline can route on the
// stable top-level keys instead of parsing free-text `console.log` output.
//
// Deliberately tiny — game-server's needs are lifecycle (listen/shutdown) + the
// WS audit sink. Trace-id correlation (LG-2) is a later add when the WS transport
// grows OTel context; for now this just kills the bare `console.*`.

type Level = 'info' | 'warn' | 'error';

function emit(level: Level, msg: string, fields?: Record<string, unknown>): void {
  const line = JSON.stringify({
    ts: new Date().toISOString(),
    level,
    service: 'game-server',
    msg,
    ...fields,
  });
  // stderr for warn/error, stdout otherwise — the ONE place a raw stream write is
  // allowed (this IS the logger). eslint-disable is scoped to these two lines.
  if (level === 'error' || level === 'warn') {
    // eslint-disable-next-line no-console
    console.error(line);
  } else {
    // eslint-disable-next-line no-console
    console.log(line);
  }
}

export const log = {
  info: (msg: string, fields?: Record<string, unknown>) => emit('info', msg, fields),
  warn: (msg: string, fields?: Record<string, unknown>) => emit('warn', msg, fields),
  error: (msg: string, fields?: Record<string, unknown>) => emit('error', msg, fields),
  /** Raw JSON-line writer for a caller that already built its own object (the WS
   *  audit sink emits a pre-shaped `{audit, service, ...event}` line). */
  line: (s: string) => {
    // eslint-disable-next-line no-console
    console.log(s);
  },
};
