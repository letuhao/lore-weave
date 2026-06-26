// LOOM Composition (T5.4 M1) — the windowing host.
//
// Sits ABOVE the studio panel layer and owns the hoisted live state
// (LiveStateProvider) + the layout model (WorkspaceLayoutProvider). The actual
// dock rail / floating windows / OS pop-out arrive in M2–M4; in M1 the shell just
// establishes the providers and renders its children (the existing CompositionPanel)
// UNCHANGED — proving the hoist + providers don't regress the studio.
//
// The feature flag (per-device, default OFF) lives in WorkspaceLayoutContext; even
// flag-OFF we mount the providers so the co-writer stream is hoisted for everyone
// (a behaviour-neutral move — ComposeView reads the same stream, now via context).
import type { ReactNode } from 'react';
import { LiveStateProvider } from '../../context/LiveStateContext';
import { CriticStateProvider } from '../../context/CriticStateContext';
import { AssembleStateProvider } from '../../context/AssembleStateContext';
import { WorkspaceLayoutProvider } from '../../context/WorkspaceLayoutContext';

export function WorkspaceShell({ token, bookId, chapterId, children }: {
  token: string | null; bookId: string; chapterId?: string; children: ReactNode;
}) {
  return (
    <WorkspaceLayoutProvider token={token}>
      {/* key={bookId} resets the hoisted co-writer stream on a book change — the
          stream USED to live inside CompositionPanel (which is key={bookId}), so the
          hoist would otherwise leak a streaming ghost/jobId from one book into the
          next. Keying only the LiveStateProvider preserves that reset without churning
          the (per-device, persisted) layout provider. /review-impl M1. */}
      <LiveStateProvider key={bookId} token={token}>
        {/* WS-B1: the latest critic verdict is shared here (above the dock/float layer)
            so the standing `critic` SubTab panel reads what ComposeView/Assemble wrote.
            Inside the book-keyed LiveStateProvider → the verdict resets on book change.
            A POPPED-OUT panel (separate root, no this provider) re-fetches by jobId. */}
        <CriticStateProvider>
          {/* WS-D: the Assemble draft is owned here (above the dock/float layer) and
              synced cross-window over the channel, so popping out the Assemble panel
              mid-draft keeps the un-accepted result + edits. key={chapterId} resets the
              draft on a chapter change (a new chapter is a new draft). */}
          <AssembleStateProvider key={chapterId} bookId={bookId} chapterId={chapterId}>
            {/* M1: render the studio as-is. M2+ swaps this for the dock/float/popout host
                when the flag is ON, keeping `children` (the fixed strip) as the OFF fallback. */}
            {children}
          </AssembleStateProvider>
        </CriticStateProvider>
      </LiveStateProvider>
    </WorkspaceLayoutProvider>
  );
}
