import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FormDialog } from '@/components/shared';
import { useResolvedSchema } from '../hooks/useResolvedSchema';
import type { TriageItemType } from '../types/ontology';

// S-05b (F4) — the `map` code picker that replaces the raw-code `window.prompt`.
// The off-schema element is MAPPED onto an EXISTING valid code, chosen from a
// select over the project's effective schema (never free text): edge types for an
// unknown edge, node kinds for an unknown kind, the set's vocab values for an
// unknown value. "Keep the detected value" (blank) is an explicit option — the
// backend then falls back to the parked value.

export interface TriageMapDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  itemType: TriageItemType;
  payload: Record<string, unknown> | undefined;
  /** null = keep the detected value (send no map_to); a string = map onto that code. */
  onPick: (code: string | null) => void;
}

export function TriageMapDialog({
  open,
  onOpenChange,
  projectId,
  itemType,
  payload,
  onPick,
}: TriageMapDialogProps) {
  const { t } = useTranslation('knowledge');
  const { schema } = useResolvedSchema(open ? projectId : null);
  const [code, setCode] = useState('');

  useEffect(() => {
    if (open) setCode('');
  }, [open]);

  const codes = useMemo<string[]>(() => {
    if (!schema) return [];
    if (itemType === 'unknown_edge_type') return (schema.edge_types ?? []).map((e) => e.code);
    if (itemType === 'unknown_node_kind') return (schema.node_kinds ?? []).map((k) => k.code);
    if (itemType === 'unknown_vocab_value') {
      const set = typeof payload?.set_code === 'string' ? (payload.set_code as string) : '';
      return (schema.vocab_values?.[set] ?? []).map((v) => v.code);
    }
    return [];
  }, [schema, itemType, payload]);

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t('triage.map.title')}
      description={t('triage.map.description')}
      footer={
        <>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-secondary"
          >
            {t('triage.map.cancel')}
          </button>
          <button
            type="button"
            onClick={() => {
              onPick(code || null);
              onOpenChange(false);
            }}
            data-testid="triage-map-confirm"
            className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            {t('triage.map.confirm')}
          </button>
        </>
      }
    >
      <label className="flex flex-col gap-1 text-[12px]">
        <span className="text-[11px] font-medium text-muted-foreground">
          {t('triage.map.label')}
        </span>
        <select
          value={code}
          onChange={(e) => setCode(e.target.value)}
          className="rounded-md border bg-input px-3 py-2 text-xs outline-none focus:border-ring"
          data-testid="triage-map-select"
        >
          <option value="">{t('triage.map.keepDetected')}</option>
          {codes.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </label>
    </FormDialog>
  );
}
