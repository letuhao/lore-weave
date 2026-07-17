import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { AlertTriangle, X, ChevronRight, ChevronDown } from 'lucide-react';
import { useTriageQueue, useTriageItems } from '../hooks/useTriageQueue';
import { triageEvidence } from '../lib/triageEvidence';
import { TriageRetargetDialog } from './TriageRetargetDialog';
import { TriageMapDialog } from './TriageMapDialog';
import type { TriageAction, TriageGroup } from '../types/ontology';

// S-05 Part B — the KG extraction-triage queue. Extraction elements that didn't
// match the resolved schema are parked (NOT written to Neo4j) and resolved
// human-gated, grouped by `signature` so one resolution batch-applies.
//
// THE LOAD-BEARING UX RULE (spec B.2): each group offers ONLY the actions the
// backend permits for its `item_type` (`suggested_actions`) — a closed set the
// router will accept — so the human never picks an action that would 400/422.
// This is the Frontend-Tool-Contract discipline applied to a human surface. We
// additionally intersect with the actions the FE knows how to DRIVE
// (`RENDERABLE_ACTIONS`), so a backend value the FE can't handle never renders a
// dead button (e.g. `place_edge`, which is a confirm-token flow, not a resolve).

// The actions the RESOLVE route completes on click. add_to_vocab / add_to_schema
// now WRITE the schema for real (S-05, D-KG-LH-LC-SCHEMA-WRITE done for the human
// path — the resolve route applies the ontology mutation, deriving the code from
// the parked payload). widen_target_kinds / set_multi_active stay OUT: their params
// aren't cleanly one-click-derivable from the parked payload (endpoint-kind /
// cardinality choices), so they remain on the agent confirm-token path for now.
const RENDERABLE_ACTIONS: ReadonlySet<TriageAction> = new Set<TriageAction>([
  'map',
  're_target',
  'drop_edge',
  'close_previous',
  'add_to_vocab',
  'add_to_schema',
  'promote_to_glossary_kind',
  'demote_to_attribute',
  'dismiss',
]);

// Schema-mutating actions get a light confirm — they change the ONTOLOGY (affect
// every future extraction), so a stray click shouldn't silently alter the schema.
const SCHEMA_MUTATING: ReadonlySet<TriageAction> = new Set<TriageAction>([
  'add_to_vocab',
  'add_to_schema',
]);

const GLOSSARY_HANDOFF: ReadonlySet<TriageAction> = new Set<TriageAction>([
  'promote_to_glossary_kind',
  'demote_to_attribute',
]);


export interface TriageQueueProps {
  projectId: string;
  bookId?: string | null;
  /** Wired by the studio panel to deep-link into glossary on a handoff action. */
  onGlossaryHandoff?: (needs: { book_id?: string | null; kinds: string[] }) => void;
}

/** S-05 — expandable per-item drill-in: dismiss ONE noisy item of a signature
 *  (via dismissTriageItem) instead of the whole group. Loaded lazily on expand. */
function GroupDrillIn({
  projectId,
  signature,
  onDismissItem,
  isDismissing,
}: {
  projectId: string;
  signature: string;
  onDismissItem: (triageId: string) => void;
  isDismissing: boolean;
}) {
  const { t } = useTranslation('knowledge');
  const { items, isLoading } = useTriageItems(projectId, signature, true);
  if (isLoading) {
    return (
      <p className="mt-2 pl-5 text-[11px] text-muted-foreground">{t('triage.loading')}</p>
    );
  }
  return (
    <ul className="mt-2 space-y-1 border-l pl-3" data-testid="kg-triage-items">
      {items.map((it) => (
        <li
          key={it.triage_id}
          className="flex items-center gap-2 text-[11px]"
          data-testid="kg-triage-item"
        >
          <span className="min-w-0 flex-1 truncate text-muted-foreground">
            {/* S-05b (F3) — humanized, never raw JSON */}
            {triageEvidence(t, it.item_type, it.payload)}
          </span>
          <button
            type="button"
            onClick={() => onDismissItem(it.triage_id)}
            disabled={isDismissing}
            title={t('triage.action.dismiss')}
            aria-label={t('triage.action.dismiss')}
            className="inline-flex shrink-0 items-center rounded-sm p-0.5 text-muted-foreground transition-colors hover:text-destructive disabled:opacity-50"
            data-testid="kg-triage-item-dismiss"
          >
            <X className="h-3 w-3" />
          </button>
        </li>
      ))}
    </ul>
  );
}

export function TriageQueue({ projectId, bookId, onGlossaryHandoff }: TriageQueueProps) {
  const { t } = useTranslation('knowledge');
  const { groups, isLoading, error, resolve, isResolving, dismissItem, isDismissing } =
    useTriageQueue(projectId);
  const [expanded, setExpanded] = useState<string | null>(null);
  // S-05b — the group currently being re-targeted (F1) / mapped (F4) via a dialog.
  const [retargetSig, setRetargetSig] = useState<string | null>(null);
  const [mapGroup, setMapGroup] = useState<TriageGroup | null>(null);

  const handleDismissItem = async (triageId: string) => {
    try {
      await dismissItem(triageId);
      toast.success(t('triage.itemDismissed'));
    } catch (e) {
      toast.error(t('triage.resolveFailed', { error: (e as Error).message }));
    }
  };

  // The shared resolve+toast path (used by the action buttons AND the re-target
  // picker), including the glossary-handoff 422 recovery.
  const runResolve = async (
    signature: string,
    action: TriageAction,
    params?: Record<string, unknown>,
  ) => {
    try {
      const result = await resolve({ signature, action, params });
      if (result.status === 'pending_glossary' && result.needs_glossary) {
        onGlossaryHandoff?.(result.needs_glossary);
        toast.info(t('triage.handoffToGlossary'));
      } else {
        toast.success(t('triage.resolved', { count: result.affected }));
      }
    } catch (e) {
      // The glossary handoff returns HTTP 422 with the needs_glossary body (the
      // shared apiJson throws `.status===422` + `.body`). Recover it into the
      // deep-link instead of surfacing a scary error.
      const err = e as { status?: number; body?: unknown };
      if (err.status === 422 && err.body && typeof err.body === 'object') {
        const body = err.body as {
          needs_glossary?: { book_id?: string | null; kinds: string[] };
        };
        if (body.needs_glossary) {
          onGlossaryHandoff?.(body.needs_glossary);
          toast.info(t('triage.handoffToGlossary'));
          return;
        }
      }
      toast.error(t('triage.resolveFailed', { error: (e as Error).message }));
    }
  };

  const handleAction = async (group: TriageGroup, action: TriageAction) => {
    // S-05b (F1) — re_target opens the entity PICKER (no more UUID prompt).
    if (action === 're_target') {
      setRetargetSig(group.signature);
      return;
    }
    // S-05b (F4) — map opens a code SELECT over the schema (no more raw-code prompt).
    if (action === 'map') {
      setMapGroup(group);
      return;
    }
    // Schema-mutating actions change the ontology — confirm before firing.
    if (SCHEMA_MUTATING.has(action) && !window.confirm(t('triage.confirmSchemaWrite'))) {
      return;
    }
    await runResolve(group.signature, action);
  };

  if (isLoading) {
    return (
      <p className="text-[12px] text-muted-foreground" data-testid="kg-triage-loading">
        {t('triage.loading')}
      </p>
    );
  }
  if (error) {
    return (
      <div
        role="alert"
        className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-[12px] text-destructive"
        data-testid="kg-triage-error"
      >
        {t('triage.loadFailed', { error: error.message })}
      </div>
    );
  }
  if (groups.length === 0) {
    return (
      <div
        className="rounded-md border border-dashed px-3 py-8 text-center text-[12px] text-muted-foreground"
        data-testid="kg-triage-empty"
      >
        {t('triage.empty')}
      </div>
    );
  }

  return (
    <>
    <ul className="space-y-2" data-testid="kg-triage-list" data-book-id={bookId ?? ''}>
      {groups.map((group) => {
        const actions = (group.suggested_actions ?? []).filter(
          (a): a is TriageAction => RENDERABLE_ACTIONS.has(a as TriageAction),
        );
        return (
          <li
            key={group.signature}
            className="rounded-md border px-3 py-2"
            data-testid="kg-triage-group"
            data-item-type={group.item_type}
          >
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="text-[12px] font-medium">
                  {t(`triage.itemType.${group.item_type}`, {
                    defaultValue: group.item_type,
                  })}
                  {/* expand toggle — only when the group has >1 item (per-item
                      dismiss only makes sense when there's more than one). */}
                  {group.count > 1 ? (
                    <button
                      type="button"
                      onClick={() =>
                        setExpanded((s) => (s === group.signature ? null : group.signature))
                      }
                      className="ml-1.5 inline-flex items-center gap-0.5 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground transition-colors hover:text-foreground"
                      data-testid="kg-triage-expand"
                    >
                      {expanded === group.signature ? (
                        <ChevronDown className="h-3 w-3" />
                      ) : (
                        <ChevronRight className="h-3 w-3" />
                      )}
                      {group.count}
                    </button>
                  ) : (
                    <span className="ml-1.5 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      {group.count}
                    </span>
                  )}
                </p>
                <p
                  className="mt-0.5 truncate text-[11px] text-muted-foreground"
                  title={triageEvidence(t, group.item_type, group.sample_payload)}
                  data-testid="kg-triage-evidence"
                >
                  {/* S-05b (F3) — humanized sentence, never raw JSON */}
                  {triageEvidence(t, group.item_type, group.sample_payload)}
                </p>
              </div>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {actions.map((action) => {
                const isHandoff = GLOSSARY_HANDOFF.has(action);
                const isDismiss = action === 'dismiss';
                return (
                  <button
                    key={action}
                    type="button"
                    onClick={() => handleAction(group, action)}
                    disabled={isResolving}
                    className={
                      'inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] transition-colors disabled:cursor-not-allowed disabled:opacity-50 ' +
                      (isDismiss
                        ? 'text-muted-foreground hover:bg-secondary'
                        : isHandoff
                          ? 'border-primary/40 text-primary hover:bg-primary/10'
                          : 'hover:bg-secondary')
                    }
                    data-testid={`kg-triage-action-${action}`}
                  >
                    {isDismiss && <X className="h-3 w-3" />}
                    {t(`triage.action.${action}`, { defaultValue: action })}
                  </button>
                );
              })}
            </div>
            {expanded === group.signature && (
              <GroupDrillIn
                projectId={projectId}
                signature={group.signature}
                onDismissItem={handleDismissItem}
                isDismissing={isDismissing}
              />
            )}
          </li>
        );
      })}
    </ul>
    {/* S-05b (F1) — the entity picker for re_target (replaces the UUID prompt). */}
    <TriageRetargetDialog
      open={retargetSig !== null}
      onOpenChange={(o) => { if (!o) setRetargetSig(null); }}
      projectId={projectId}
      onPick={(entityId) => {
        const sig = retargetSig;
        setRetargetSig(null);
        if (sig) void runResolve(sig, 're_target', { target_entity_id: entityId });
      }}
    />
    {/* S-05b (F4) — the code select for map (replaces the raw-code prompt). */}
    {mapGroup && (
      <TriageMapDialog
        open
        onOpenChange={(o) => { if (!o) setMapGroup(null); }}
        projectId={projectId}
        itemType={mapGroup.item_type}
        payload={mapGroup.sample_payload}
        onPick={(code) => {
          const sig = mapGroup.signature;
          setMapGroup(null);
          void runResolve(sig, 'map', code ? { map_to: code } : {});
        }}
      />
    )}
    </>
  );
}
