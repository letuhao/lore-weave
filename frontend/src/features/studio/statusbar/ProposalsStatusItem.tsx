// S-12 · D-S12-STUDIO-PROPOSAL-BADGE — a frame-level "pending approvals" badge. Lives at
// frame level (NOT in a proposals panel) so the count stays live while both panels are
// closed — the whole point (a proposal an agent minted is discoverable when the user
// returns, not only if they happen to open the panel). Mirrors NotificationsStatusItem.
//
// Covers BOTH proposal types with ONE badge: the count is skill + workflow (from the split
// /usage counts); clicking routes to the panel that actually has pending items — workflow
// first (the S-12 gap), else the skill proposals inbox.
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Inbox } from 'lucide-react';
import { useAuth } from '@/auth';
import { extensionsApi } from '@/features/extensions/api';
import { useStudioHost } from '../host/StudioHostProvider';
import { getStudioPanelDef } from '../panels/catalog';

const POLL_MS = 45_000; // ambient indicator — a short lag is fine; not a critical counter.

export function ProposalsStatusItem() {
  const { t } = useTranslation('studio');
  const { accessToken } = useAuth();
  const host = useStudioHost();
  const [skill, setSkill] = useState(0);
  const [workflow, setWorkflow] = useState(0);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    try {
      const u = await extensionsApi.usage(accessToken);
      // Split fields are optional (older responses) — fall back to the summed total on skill.
      setWorkflow(u.workflow_proposals_pending ?? 0);
      setSkill(u.skill_proposals_pending ?? (u.workflow_proposals_pending == null ? u.proposals_pending : 0));
    } catch {
      /* badge is cosmetic; the panels show the truth */
    }
  }, [accessToken]);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), POLL_MS);
    const onFocus = () => void refresh();
    window.addEventListener('focus', onFocus);
    return () => { window.clearInterval(id); window.removeEventListener('focus', onFocus); };
  }, [refresh]);

  const total = skill + workflow;
  if (total === 0) return null; // nothing pending → no badge (like the unread bell)

  const openPanel = () => {
    // Route to the panel that has pending items; prefer workflow-proposals (the S-12 gap).
    const panelId = workflow > 0 ? 'workflow-proposals' : 'proposals';
    const def = getStudioPanelDef(panelId);
    host.openPanel(panelId, { title: def ? t(def.titleKey, { defaultValue: panelId }) : undefined });
    void refresh();
  };

  return (
    <button
      type="button"
      data-testid="studio-status-proposals"
      onClick={openPanel}
      title={t('status.proposalsPending', { count: total, defaultValue: '{{count}} pending approval(s)' })}
      className="inline-flex items-center gap-1 rounded px-1 py-0.5 hover:bg-secondary hover:text-foreground"
    >
      <Inbox className="h-3 w-3" />
      <span
        data-testid="studio-status-proposals-count"
        className="flex h-[14px] min-w-[14px] items-center justify-center rounded-full bg-amber-500 px-0.5 text-[9px] font-bold text-white"
      >
        {total > 99 ? '99+' : total}
      </span>
    </button>
  );
}
