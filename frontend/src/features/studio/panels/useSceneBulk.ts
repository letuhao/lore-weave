// 22-C2b — the scene-browser's bulk-triage controller (no JSX). Selection + apply a spec change
// (status) or trash across many scenes at once (spec 22 §GUI: "Bulk-select → set status, retarget
// words, trash — writes target the SPEC via composition_outline_node_update"). Bulk edits hit
// DISTINCT nodes (each with its own OCC version), so they fan out in parallel — there is no
// same-entity single-flight race (unlike the inspector's Cast&Setting fields on ONE node). Partial
// failure is reported honestly: a 412 (someone edited that scene) is a conflict, not a silent drop.
import { useCallback, useState } from 'react';
import { compositionApi } from '@/features/composition/api';
import type { OutlineNode } from '@/features/composition/types';

/** One bulk target — the node id + the OCC version to send as If-Match. */
export type BulkTarget = { id: string; version: number };
export type BulkResult = { ok: number; conflicts: number; failed: number };

export type SceneBulkState = {
  selected: ReadonlySet<string>;
  busy: boolean;
  result: BulkResult | null;
  toggle: (id: string) => void;
  setMany: (ids: string[], on: boolean) => void;
  clear: () => void;
  /** Patch a spec field (status, target_words…) across the targets; OCC per node. */
  apply: (targets: BulkTarget[], patch: Partial<OutlineNode>) => Promise<void>;
  /** Soft-archive the targets. */
  trash: (targets: BulkTarget[]) => Promise<void>;
};

export function useSceneBulk(token: string | null, reload: () => void): SceneBulkState {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<BulkResult | null>(null);

  const toggle = useCallback((id: string) => {
    setResult(null);
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  const setMany = useCallback((ids: string[], on: boolean) => {
    setResult(null);
    setSelected((prev) => {
      const next = new Set(prev);
      for (const id of ids) { if (on) next.add(id); else next.delete(id); }
      return next;
    });
  }, []);

  const clear = useCallback(() => { setSelected(new Set()); setResult(null); }, []);

  const runBulk = useCallback(async (targets: BulkTarget[], op: (t: BulkTarget) => Promise<unknown>) => {
    if (!token || targets.length === 0) return;
    setBusy(true); setResult(null);
    const settled = await Promise.allSettled(targets.map(op));
    let ok = 0, conflicts = 0, failed = 0;
    for (const r of settled) {
      if (r.status === 'fulfilled') ok += 1;
      else if ((r.reason as { status?: number })?.status === 412) conflicts += 1;
      else failed += 1;
    }
    setBusy(false);
    setResult({ ok, conflicts, failed });
    setSelected(new Set()); // rows may have moved/archived — clear so a stale selection can't re-apply
    reload();
  }, [token, reload]);

  const apply = useCallback((targets: BulkTarget[], patch: Partial<OutlineNode>) =>
    runBulk(targets, (t) => compositionApi.patchNode(t.id, patch, token!, t.version)), [runBulk, token]);

  const trash = useCallback((targets: BulkTarget[]) =>
    runBulk(targets, (t) => compositionApi.archiveNode(t.id, token!)), [runBulk, token]);

  return { selected, busy, result, toggle, setMany, clear, apply, trash };
}
