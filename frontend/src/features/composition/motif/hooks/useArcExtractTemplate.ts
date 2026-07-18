// S-10 O6a — the "Save this arc as a template" controller. Extracts an AUTHORED arc (structure_node)
// into the caller's own arc-template library via POST /arcs/{nodeId}/extract-template. A 409
// (ARC_TEMPLATE_CODE_EXISTS — a template with that code+language already exists) is surfaced as
// `conflict` so the widget can ask for a different code. On success it invalidates the arc-template
// library list so the new template shows up. No JSX.
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { arcApi, type ArcExtractArgs } from '../arcApi';
import type { ArcTemplate } from '../arcTypes';

export function useArcExtractTemplate(nodeId: string | null, token: string | null) {
  const qc = useQueryClient();
  const mut = useMutation<ArcTemplate, Error & { status?: number }, ArcExtractArgs>({
    mutationFn: (args) => arcApi.extractTemplate(nodeId!, args, token!),
    onSuccess: () => {
      // the new template joins the caller's library — refresh any arc-template list.
      qc.invalidateQueries({ queryKey: ['composition', 'arc-templates'] });
    },
  });
  return {
    run: (args: ArcExtractArgs) => mut.mutate(args),
    result: mut.data,
    isPending: mut.isPending,
    isError: mut.isError,
    // 409 — the (owner, code, language) already exists; the widget asks for a new code.
    conflict: (mut.error as { status?: number } | null)?.status === 409,
    reset: mut.reset,
  };
}

// Derive a stable, server-valid `code` slug from a name (lower, non-alnum → single '_', trimmed,
// capped at 120 to mirror the route's SchemaCode bound). Empty → 'arc' so submit is never blocked
// on an all-punctuation name.
export function slugifyArcCode(name: string): string {
  const slug = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  return (slug || 'arc').slice(0, 120);
}
