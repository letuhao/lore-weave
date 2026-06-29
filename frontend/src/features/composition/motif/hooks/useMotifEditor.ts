// WI-2 (D-MOTIF-FULL-EDITOR-FE) — the full owned-motif editor controller. Seeds an
// editable copy from a fetched Motif, tracks dirtiness + the optimistic-lock version, and
// PATCHes the owner-only route (re-embed fires server-side on a summary change). A 412
// (someone else bumped the row) surfaces a conflict so the user reloads rather than
// clobbering. No JSX — MotifEditorForm renders. The detail drawer covers VIEW + clone-to-
// edit for shared rows; this is the missing in-place editor for your OWN motifs.
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { motifApi } from '../api';
import type {
  Actant, InfoAsymmetry, Motif, MotifBeat, MotifKind, MotifPatchArgs, MotifRole,
} from '../types';

export type MotifEditState = {
  name: string;
  kind: MotifKind;
  summary: string;
  genres: string;               // comma-separated (parsed on submit)
  tension_target: number | null;
  emotion_target: string;
  roles: MotifRole[];
  beats: MotifBeat[];
  preconditions: string[];      // free-text NL
  effects: string[];
  examples: string[];           // author-written (stripped on imported-derived publish)
  info_asymmetry: InfoAsymmetry | null;   // scheme only
};

function fromMotif(m: Motif): MotifEditState {
  return {
    name: m.name,
    kind: m.kind,
    summary: m.summary,
    genres: m.genre_tags.join(', '),
    tension_target: m.tension_target,
    emotion_target: m.emotion_target ?? '',
    roles: m.roles.map((r) => ({ ...r })),
    beats: [...m.beats].sort((a, b) => a.order - b.order).map((b) => ({ ...b })),
    preconditions: m.preconditions.map((p) => p.text),
    effects: m.effects.map((e) => e.text),
    examples: m.examples.map((e) => e.text),
    info_asymmetry: m.info_asymmetry ? { ...m.info_asymmetry } : null,
  };
}

function toArgs(s: MotifEditState): MotifPatchArgs {
  return {
    name: s.name.trim(),
    kind: s.kind,
    summary: s.summary.trim(),
    genre_tags: s.genres.split(',').map((g) => g.trim()).filter(Boolean),
    tension_target: s.tension_target,
    emotion_target: s.emotion_target.trim() || null,
    roles: s.roles.filter((r) => r.label.trim() || r.key.trim()),
    beats: s.beats.filter((b) => b.label.trim()).map((b, i) => ({ ...b, label: b.label.trim(), order: i })),
    preconditions: s.preconditions.map((t) => t.trim()).filter(Boolean).map((text) => ({ text })),
    effects: s.effects.map((t) => t.trim()).filter(Boolean).map((text) => ({ text })),
    examples: s.examples.map((t) => t.trim()).filter(Boolean).map((text) => ({ text })),
    // a scheme's info_asymmetry rides along; non-schemes never send it
    ...(s.kind === 'scheme' && s.info_asymmetry ? { info_asymmetry: s.info_asymmetry } : {}),
  };
}

export function useMotifEditor(motif: Motif | null, token: string | null, onSaved?: (m: Motif) => void) {
  const qc = useQueryClient();
  const [form, setForm] = useState<MotifEditState | null>(motif ? fromMotif(motif) : null);
  const [seed, setSeed] = useState<string>('');
  const [conflict, setConflict] = useState(false);

  // Re-seed only when the motif IDENTITY changes (open a different motif). NOT on a
  // version bump — a background refetch (e.g. a list invalidation) must NOT clobber the
  // user's in-progress edits. A genuinely stale save is caught by the 412 optimistic lock
  // → conflict surface, not by silently re-seeding underneath the editor.
  useEffect(() => {
    if (motif) {
      const s = fromMotif(motif);
      setForm(s);
      setSeed(JSON.stringify(s));
      setConflict(false);
    } else {
      setForm(null);
    }
  }, [motif?.id]);   // eslint-disable-line react-hooks/exhaustive-deps

  const set = <K extends keyof MotifEditState>(k: K, v: MotifEditState[K]) =>
    setForm((p) => (p ? { ...p, [k]: v } : p));

  // ── roles ──
  const addRole = () => set('roles', [...(form?.roles ?? []), { key: `role_${(form?.roles.length ?? 0) + 1}`, actant: 'subject', label: '' }]);
  const setRole = (i: number, patch: Partial<MotifRole>) => set('roles', (form?.roles ?? []).map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const removeRole = (i: number) => set('roles', (form?.roles ?? []).filter((_, j) => j !== i));

  // ── beats (reorderable) ──
  const addBeat = () => set('beats', [...(form?.beats ?? []), { key: `beat_${(form?.beats.length ?? 0) + 1}`, label: '', order: form?.beats.length ?? 0 }]);
  const setBeat = (i: number, patch: Partial<MotifBeat>) => set('beats', (form?.beats ?? []).map((b, j) => (j === i ? { ...b, ...patch } : b)));
  const removeBeat = (i: number) => set('beats', (form?.beats ?? []).filter((_, j) => j !== i));
  const moveBeat = (i: number, dir: -1 | 1) => {
    const beats = [...(form?.beats ?? [])];
    const j = i + dir;
    if (j < 0 || j >= beats.length) return;
    [beats[i], beats[j]] = [beats[j], beats[i]];
    set('beats', beats);
  };

  // ── list fields (preconditions / effects / examples) ──
  const listOps = (k: 'preconditions' | 'effects' | 'examples') => ({
    add: () => set(k, [...(form?.[k] ?? []), '']),
    setAt: (i: number, v: string) => set(k, (form?.[k] ?? []).map((x, j) => (j === i ? v : x))),
    removeAt: (i: number) => set(k, (form?.[k] ?? []).filter((_, j) => j !== i)),
  });

  const setInfoAsymmetry = (patch: Partial<InfoAsymmetry>) =>
    set('info_asymmetry', { knows: [], deceived: [], gap: '', ...(form?.info_asymmetry ?? {}), ...patch });

  const dirty = !!form && JSON.stringify(form) !== seed;
  const canSubmit = !!form && form.name.trim().length > 0 && dirty;

  const save = useMutation({
    mutationFn: () => motifApi.patch(motif!.id, toArgs(form!), motif!.version, token!),
    onSuccess: (m) => {
      qc.invalidateQueries({ queryKey: ['composition', 'motifs'] });
      qc.invalidateQueries({ queryKey: ['composition', 'motif', m.id] });
      setSeed(JSON.stringify(fromMotif(m)));
      onSaved?.(m);
    },
    onError: (err: unknown) => {
      // 412 Precondition Failed → the row was edited elsewhere; force a reload, don't clobber.
      const status = (err as { status?: number; body?: { code?: number } } | null)?.status;
      if (status === 412) setConflict(true);
    },
  });

  const actants = useMemo<Actant[]>(() => ['subject', 'object', 'sender', 'receiver', 'helper', 'opponent'], []);

  return {
    form, set, dirty, canSubmit, conflict,
    addRole, setRole, removeRole,
    addBeat, setBeat, removeBeat, moveBeat,
    preconditions: listOps('preconditions'),
    effects: listOps('effects'),
    examples: listOps('examples'),
    setInfoAsymmetry,
    actants,
    save,
  };
}
