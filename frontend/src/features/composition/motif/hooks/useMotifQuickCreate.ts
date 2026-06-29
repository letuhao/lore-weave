// W6 §3.2 — the manual-build quick-create form controller (the §3.5 baseline-not-
// fallback principle: building a motif by hand is free, no tokens). Owns the form
// state (name/kind/genre + beats array with add/remove) + submit. No JSX.
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo, useState } from 'react';
import { motifApi } from '../api';
import type { Motif, MotifBeat, MotifKind } from '../types';

export type QuickCreateState = {
  name: string;
  code: string;
  kind: MotifKind;
  summary: string;
  genres: string;        // comma-separated (parsed on submit)
  tension: number | null;
  beats: Array<{ key: string; label: string }>;
};

const EMPTY: QuickCreateState = {
  name: '', code: '', kind: 'sequence', summary: '', genres: '', tension: null, beats: [],
};

export function useMotifQuickCreate(token: string | null, onCreated?: (m: Motif) => void) {
  const qc = useQueryClient();
  const [form, setForm] = useState<QuickCreateState>(EMPTY);

  const set = useCallback(<K extends keyof QuickCreateState>(k: K, v: QuickCreateState[K]) => {
    setForm((prev) => ({ ...prev, [k]: v }));
  }, []);

  const addBeat = useCallback(() => {
    setForm((prev) => ({ ...prev, beats: [...prev.beats, { key: `beat_${prev.beats.length + 1}`, label: '' }] }));
  }, []);
  const setBeat = useCallback((i: number, label: string) => {
    setForm((prev) => ({ ...prev, beats: prev.beats.map((b, j) => (j === i ? { ...b, label } : b)) }));
  }, []);
  const removeBeat = useCallback((i: number) => {
    setForm((prev) => ({ ...prev, beats: prev.beats.filter((_, j) => j !== i) }));
  }, []);
  const reset = useCallback(() => setForm(EMPTY), []);

  // A submittable form needs a name + code + at least the implicit summary.
  const canSubmit = form.name.trim().length > 0 && form.code.trim().length > 0;

  const create = useMutation({
    mutationFn: () => {
      const beats: MotifBeat[] = form.beats
        .filter((b) => b.label.trim())
        .map((b, i) => ({ key: b.key, label: b.label.trim(), order: i }));
      return motifApi.create(
        {
          code: form.code.trim(),
          name: form.name.trim(),
          kind: form.kind,
          summary: form.summary.trim(),
          genre_tags: form.genres.split(',').map((g) => g.trim()).filter(Boolean),
          beats,
          tension_target: form.tension,
        },
        token!,
      );
    },
    onSuccess: (m) => {
      qc.invalidateQueries({ queryKey: ['composition', 'motifs'] });
      reset();
      onCreated?.(m);
    },
  });

  const fieldErrors = useMemo(() => {
    const errs: Partial<Record<keyof QuickCreateState, string>> = {};
    if (!form.name.trim()) errs.name = 'motif.create.err.name';
    if (!form.code.trim()) errs.code = 'motif.create.err.code';
    return errs;
  }, [form.name, form.code]);

  return { form, set, addBeat, setBeat, removeBeat, reset, canSubmit, create, fieldErrors };
}
