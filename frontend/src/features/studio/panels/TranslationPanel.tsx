// 17_translation_enrichment_sharing_settings_docks.md — the `translation` dock panel: the
// coverage matrix (chapters × languages), language filter, chapter multi-select, bulk
// translate/extract triggers, and legend. Thin wrapper reusing the classic TranslationTab AS-IS
// (DOCK-2), resolving book_id from the studio host instead of a route param (DOCK-7). The
// matrix-cell "manage versions" action opens the new `translation-versions` sibling panel
// instead of navigating to the classic per-chapter route (DOCK-7 — the studio never unmounts
// itself to satisfy one panel's link). No `mcpToolPrefixes` registered here — translation-service
// DOES federate MCP tools through ai-gateway (`translation_*`, confirmed 2026-07-05's LIVE-SYNC
// audit; the prior "no MCP tools federated" claim here was stale) but this panel never wired the
// agent-rack attribution; tracked as a separate, smaller gap, not blocking (the reconciler's
// `translation_job_control` effect handler covers the actual live-sync need independently).
import type { IDockviewPanelProps } from 'dockview-react';
import { TranslationTab } from '@/pages/book-tabs/TranslationTab';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function TranslationPanel(props: IDockviewPanelProps) {
  useStudioPanel('translation', props.api);
  const host = useStudioHost();

  return (
    <div data-testid="studio-translation-panel" className="h-full min-h-0 overflow-auto">
      <TranslationTab
        bookId={host.bookId}
        onManageVersions={(chapterId, lang) =>
          host.openPanel('translation-versions', { params: { chapterId, lang } })
        }
      />
    </div>
  );
}
