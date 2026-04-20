// K19a.5 — extractor for BE error bodies surfaced by apiJson.
//
// FastAPI wraps `HTTPException(detail=...)` responses as
// `{"detail": ...}` where `detail` can be a string, dict, or list.
// The project's `apiJson` helper only reads the top-level `.message`
// on the parsed body, which is undefined for the FastAPI shape — the
// thrown Error then carries `res.statusText` ("Conflict" / "Not Found"
// / etc.) instead of the real explanation.
//
// Walk the attached `body` ourselves to pull the structured message
// when present. Falls back to `err.message` then stringification.
// Moved here from BuildGraphDialog.tsx (K19a.6) so that multiple
// dialogs can share it without cross-component imports. Exported
// separately so it's also covered by a focused pure unit test.
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
    }
    if (err.message) return err.message;
  }
  return String(err);
}
