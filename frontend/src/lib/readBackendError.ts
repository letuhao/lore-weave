// AI-Task Standard — the shared BE-error reader (was features/knowledge/lib).
//
// FastAPI wraps `HTTPException(detail=...)` as `{"detail": ...}` where `detail`
// can be a string, a dict `{message}`, or a list. Some routes instead put the
// reason at top-level `{"message": ...}`. The project's `apiJson` only reads the
// top-level `.message`, so the thrown Error otherwise carries `res.statusText`
// ("Bad Gateway" / "Conflict") instead of the real explanation.
//
// Walk the attached `body` ourselves. Order: detail-string → detail.message →
// body.message → err.message → stringify. This is the single reader every AI-task
// dialog uses so a generate failure shows WHY, not a generic status line.
export function readBackendError(err: unknown): string {
  if (err instanceof Error) {
    const body = (err as Error & { body?: unknown }).body;
    if (body && typeof body === 'object') {
      const detail = (body as { detail?: unknown }).detail;
      if (typeof detail === 'string' && detail.length > 0) return detail;
      if (detail && typeof detail === 'object' && 'message' in detail) {
        const msg = (detail as { message?: unknown }).message;
        if (typeof msg === 'string' && msg.length > 0) return msg;
      }
      const topMsg = (body as { message?: unknown }).message;
      if (typeof topMsg === 'string' && topMsg.length > 0) return topMsg;
    }
    if (err.message) return err.message;
  }
  return String(err);
}
