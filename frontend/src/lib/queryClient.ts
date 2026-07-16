// W0-S16 — the single QueryClient, with a GLOBAL mutation error handler.
//
// THE BUG THIS CLOSES: App.tsx built `new QueryClient({...})` with no MutationCache,
// so EVERY failed mutation in the entire frontend failed SILENTLY — no toast, the
// button just re-enabled. `grep MutationCache src` returned one hit and it was a
// comment; there were 142 `useMutation(` call sites and only 98 `onError` handlers,
// so ~44 mutations surfaced nothing on failure. That silence is exactly why three
// live bugs (motif-mine 500, AddModelCta dock teardown, Translate drop) survived to
// an audit. The repo already had the law — "a resolver never silently no-ops" — but
// wrote it for agent→GUI tools and never applied it to user-initiated GUI actions.
//
// THE RULE: a slice-local `onError` still WINS. If a mutation declares its own
// onError, it owns the UX (it may show inline errors, retry, etc.) and we do NOT
// double-toast. The global handler is the SAFETY NET for the ~44 that declare none.
import { QueryClient, MutationCache } from '@tanstack/react-query';
import { toast } from 'sonner';
import { readBackendError } from '@/lib/readBackendError';

export const queryClient = new QueryClient({
  mutationCache: new MutationCache({
    onError: (error, _vars, _ctx, mutation) => {
      // A mutation that declares its own onError owns its failure UX — don't clobber it.
      if (mutation.options.onError) return;
      toast.error(readBackendError(error));
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: 30 * 1000, // 30s — data considered fresh for 30s
      gcTime: 5 * 60 * 1000, // 5min — garbage collect after 5min
      refetchOnWindowFocus: true, // refetch when user returns to tab
      retry: 1,
    },
  },
});
