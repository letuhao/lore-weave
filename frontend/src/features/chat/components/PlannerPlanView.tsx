import { useTranslation } from 'react-i18next';
import { ListChecks, AlertTriangle } from 'lucide-react';
import type { ActionPreviewRow } from '../actionsApi';

/**
 * D-PLAN-PLANNER-DEFAULT-FE phase 3 — a readable "planner view" of a glossary
 * execute_plan card (the typed plan glossary_plan produced). Renders each op as a numbered
 * STEP with a human label + rationale, instead of the terse `type: op-id` rows. Destructive
 * ops keep their default-OFF opt-in checkbox (G1). Planner notes render as a trailing block.
 *
 * Render-only: the parent (ConfirmActionCard) owns the enabled-ops set + toggle.
 */

// Op label → display. In production the execute_plan PREVIEW already sends a human label
// ("create kinds", "delete genre"), which falls through to the slug-humanizer (just
// capitalized). This map is a defensive fallback for the raw op-type form (the mint path)
// so either shape reads sensibly without a FE change.
const OP_LABELS: Record<string, string> = {
  adopt_genres: 'Adopt standard genres & kinds',
  create_kinds: 'Create kinds',
  add_attributes: 'Add attributes',
  edit_attribute: 'Edit attribute',
  delete_genre: 'Delete genre',
  delete_kind: 'Delete kind',
  delete_attribute: 'Delete attribute',
  merge_candidate: 'Merge duplicate entities',
  dismiss_candidate: 'Dismiss duplicate suggestion',
};

function humanizeOp(type: string): string {
  return OP_LABELS[type] ?? type.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
}

export function PlannerPlanView({
  rows,
  enabledOps,
  onToggleOp,
  disabled,
}: {
  rows: ActionPreviewRow[];
  enabledOps: Set<string>;
  onToggleOp: (opId: string) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation('chat');
  const ops = rows.filter((r) => r.label !== 'note');
  const notes = rows.filter((r) => r.label === 'note');

  return (
    <div className="mb-1.5">
      <div className="mb-1 flex items-center gap-1.5 text-[11px] font-medium text-foreground/80">
        <ListChecks className="h-3.5 w-3.5" />
        {t('planner.heading', { defaultValue: 'Plan' })}
        <span className="text-muted-foreground">· {t('planner.steps', { defaultValue: '{{count}} step(s)', count: ops.length })}</span>
      </div>

      <ol className="space-y-1">
        {ops.map((r, i) => {
          const isDestructive = !!(r.destructive && r.op_id);
          const enabled = isDestructive && enabledOps.has(r.op_id!);
          return (
            <li
              key={r.op_id ?? i}
              className={`flex gap-2 rounded-md border px-2 py-1.5 ${
                isDestructive ? 'border-red-500/30 bg-red-500/5' : 'border-border bg-background/40'
              }`}
            >
              <span className="mt-0.5 flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full bg-secondary text-[9px] font-mono text-muted-foreground">
                {i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] font-medium text-foreground">{humanizeOp(r.label)}</span>
                  {isDestructive && (
                    <span className="inline-flex items-center gap-0.5 rounded bg-red-500/15 px-1 text-[9px] font-semibold uppercase text-red-500">
                      <AlertTriangle className="h-2.5 w-2.5" />
                      {t('planner.destructive', { defaultValue: 'destructive' })}
                    </span>
                  )}
                </div>
                {/* The concrete target / counts (BE preview puts the "what" here: a kind
                    code, an attribute path, "3 new", merge winner/losers). Must render —
                    dropping it leaves the step without its subject. */}
                {r.value && <p className="mt-0.5 break-words text-[10px] text-foreground/80">{r.value}</p>}
                {r.note && <p className="mt-0.5 text-[10px] leading-snug text-muted-foreground">{r.note}</p>}
                {isDestructive && (
                  <label className="mt-1 flex cursor-pointer items-center gap-1.5 text-[10px] text-red-500">
                    <input
                      type="checkbox"
                      data-testid="enable-op"
                      data-op-id={r.op_id}
                      checked={enabled}
                      onChange={() => onToggleOp(r.op_id!)}
                      disabled={disabled}
                      className="h-3 w-3 accent-red-500"
                    />
                    {t('planner.enable', { defaultValue: 'Enable this destructive step' })}
                  </label>
                )}
              </div>
            </li>
          );
        })}
      </ol>

      {notes.length > 0 && (
        <div className="mt-1.5 rounded-md border border-border bg-background/40 px-2 py-1.5">
          <p className="mb-0.5 text-[10px] font-medium text-muted-foreground">
            {t('planner.notes', { defaultValue: 'Planner notes' })}
          </p>
          <ul className="list-disc space-y-0.5 pl-3.5 text-[10px] text-muted-foreground">
            {notes.map((n, i) => (
              <li key={i}>{n.value}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
