// 14_kg_panels.md Phase B — the `kg-proposals` dock panel: book-scoped (host.bookId
// IS the value ProposalsInboxTab wants as `bookId` — no project resolution needed,
// unlike the project-id-scoped panels which go through useBookKnowledgeProject).
// Reuses ProposalsInboxTab AS-IS (DOCK-2) with its one behavioral change: the row
// action used to render a route link straight to `row.deepLinkUrl` (DOCK-7
// violation); it now takes an `onOpenRow` callback, and this panel wires that to
// the studio link resolver (F3 `followStudioLink`) instead of navigate() — same
// shape as KnowledgeHubPanel's `onOpen`. Every deepLinkUrl today (`/books/:id/glossary`,
// `/books/:id/wiki`, `/books/:id/enrichment`) is an unmapped app path in
// studioLinks.ts, so F3 falls through to "external" and opens the classic route
// in a new tab — not a silent no-op, and it upgrades automatically once those
// routes gain their own dock-panel mappings.
import type { IDockviewPanelProps } from 'dockview-react';
import { ProposalsInboxTab } from '@/features/knowledge/components/ProposalsInboxTab';
import type { ProposalInboxRow } from '@/features/knowledge/lib/proposalsInbox';
import { useStudioHost } from '../host/StudioHostProvider';
import { followStudioLink } from '../host/studioLinks';
import { useStudioPanel } from './useStudioPanel';

export function KgProposalsPanel(props: IDockviewPanelProps) {
  useStudioPanel('kg-proposals', props.api, { mcpToolPrefixes: ['kg_'] });
  const host = useStudioHost();

  const onOpenRow = (row: ProposalInboxRow) => {
    followStudioLink(row.deepLinkUrl, host, { bookId: host.bookId });
  };

  return (
    <div data-testid="studio-kg-proposals-panel" className="h-full min-h-0 overflow-auto p-4">
      <ProposalsInboxTab bookId={host.bookId} onOpenRow={onOpenRow} />
    </div>
  );
}
