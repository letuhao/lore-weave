import { useEffect } from 'react';
import { refreshAccessToken } from '@/api';

// MB8 — proactively refresh the access token when the tab returns to the foreground. On mobile a
// backgrounded PWA can sit idle long enough for the short-lived access token to expire; SSE/voice
// streams bypass apiJson's reactive-401 refresh, so without this a resumed stream reconnects with a
// dead token. Refreshing on `visibilitychange` (visible) means the fresh token is in auth state
// (via the 'lw-auth-refreshed' event) BEFORE anything re-subscribes. refreshAccessToken is
// single-flight, so overlapping resumes coalesce to one refresh.
export function useResumeTokenRefresh(): void {
  useEffect(() => {
    const onVisible = () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
        void refreshAccessToken();
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, []);
}
