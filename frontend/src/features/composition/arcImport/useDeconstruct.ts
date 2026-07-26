// 34 §4.3 拆文 — the Import & Deconstruct CONTROLLER (no JSX). Sources CRUD + the PRICED
// deconstruct's propose→confirm→poll (mirrors useMotifMine: the FE never executes the spend).
// AT-8: the deconstruct REQUIRES an explicit BYOK model_ref — the section forbids submit without one.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { arcImportApi, type DeconstructArgs, type ImportSource } from './api';
import type { CostEstimate } from '../motif/types';

export const IMPORT_SOURCE_MAX = 20_000;

export function useDeconstruct(token: string | null) {
  const qc = useQueryClient();
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [arcHint, setArcHint] = useState('');
  const [useWeb, setUseWeb] = useState(false);
  const [language, setLanguage] = useState('en');
  const [estimate, setEstimate] = useState<CostEstimate | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const sources = useQuery({
    queryKey: ['composition', 'import-sources'],
    queryFn: async () => (await arcImportApi.listSources(token!)).import_sources,
    enabled: !!token,
  });

  const invalidateSources = () => qc.invalidateQueries({ queryKey: ['composition', 'import-sources'] });

  const createSource = useMutation({
    mutationFn: (body: { content: string; title: string }) => arcImportApi.createSource(body, token!),
    onSuccess: (s: ImportSource) => { setSelectedSourceId(s.id); void invalidateSources(); },
  });
  const deleteSource = useMutation({
    mutationFn: (id: string) => arcImportApi.deleteSource(id, token!),
    onSuccess: (_v, id) => { setSelectedSourceId((cur) => (cur === id ? null : cur)); void invalidateSources(); },
  });

  // Step 1 — mint the cost estimate + confirm token for the chosen model (NO spend).
  const mint = useMutation({
    mutationFn: (modelRef: string) => {
      if (!selectedSourceId) throw new Error('pick a source first');
      const args: DeconstructArgs = { importSourceId: selectedSourceId, arcHint: arcHint || undefined, useWeb, language, modelRef };
      return arcImportApi.deconstructPropose(args, token!);
    },
    onSuccess: setEstimate,
  });

  // Step 2 — confirm the spend → poll the Work-less job → the new arc template; refresh the library.
  const confirm = useMutation({
    mutationFn: () => arcImportApi.deconstructConfirm(estimate!.confirm_token, token!),
    onSuccess: (r) => {
      setResult(r);
      setEstimate(null);
      void qc.invalidateQueries({ queryKey: ['composition', 'arc-templates'] });
    },
  });

  const cancel = () => setEstimate(null);
  const reset = () => { setEstimate(null); setResult(null); mint.reset(); confirm.reset(); };

  return {
    sources: sources.data ?? [], sourcesLoading: sources.isLoading, sourcesError: sources.isError,
    selectedSourceId, setSelectedSourceId,
    arcHint, setArcHint, useWeb, setUseWeb, language, setLanguage,
    createSource, deleteSource,
    estimate, result, mint, confirm, cancel, reset,
    error: (mint.error || confirm.error) as unknown,
  };
}
