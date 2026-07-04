// 17_translation_enrichment_sharing_settings_docks.md — Book Sharing dock panel. THIN wrapper
// over the existing SharingTab (visibility radio-cards, unlisted-link+rotate, and the
// CollaboratorsPanel it already mounts) — same reuse-AS-IS shape as UsagePanel/TrashPanel:
// SharingTab is already self-contained (takes `bookId` as a prop, no route-navigate hooks or
// router-Link element inside it — DOCK-7 was already clean before this port), so the only
// thing that changes here is where `bookId` comes from (the studio host instead of
// BookDetailPage's route param) plus the dock chrome (register + self-title).
import type { IDockviewPanelProps } from 'dockview-react';
import { SharingTab } from '@/pages/book-tabs/SharingTab';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function SharingPanel(props: IDockviewPanelProps) {
  useStudioPanel('sharing', props.api);
  const { bookId } = useStudioHost();

  return (
    <div data-testid="studio-sharing-panel" className="h-full min-h-0 overflow-auto">
      <SharingTab bookId={bookId} />
    </div>
  );
}
