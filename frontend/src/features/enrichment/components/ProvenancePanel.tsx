import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { providerApi } from '@/features/settings/api';
import { isRecookable, type Proposal, type SourceRef, type SkippedSource } from '../types';

/** Surfaces grounding sources (+ license), the recook abstraction (②) attribution,
 *  the generation model, and any sources the licensing gate skipped (① default-deny)
 *  — so the ©-safety story is visible to the author before they promote. */
export function ProvenancePanel({ proposal }: { proposal: Proposal }) {
  const { t } = useTranslation('enrichment');
  const { accessToken } = useAuth();
  const refs = proposal.source_refs_json ?? [];
  const prov = proposal.provenance_json ?? {};
  const skipped = prov.skipped_unlicensed_sources ?? [];
  const isRecook = proposal.technique === 'recook' || proposal.original_technique === 'recook';

  // LE-067 — the gen model_ref (a user_model_id) lives in provenance; resolve it to
  // the user's friendly alias via provider-registry (shared 'chat' models cache).
  const modelRef = prov.retrieval?.model_ref ?? prov.recook?.model_ref;
  const { data: chatModels } = useQuery({
    queryKey: ['user-models', 'chat'],
    queryFn: () => providerApi.listUserModels(accessToken!, { capability: 'chat' }),
    enabled: !!accessToken && !!modelRef,
  });
  const model = modelRef
    ? (() => {
        const m = chatModels?.items.find((x) => x.user_model_id === modelRef);
        return m?.alias || m?.provider_model_name || `${modelRef.slice(0, 8)}…`;
      })()
    : null;

  return (
    <div className="space-y-3 text-xs" data-testid="enrichment-provenance">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
        <Field label={t('prov.technique')} value={proposal.technique} mono />
        <Field label={t('prov.confidence')} value={proposal.confidence.toFixed(2)} mono />
        <Field label={t('prov.origin')} value={proposal.origin} mono />
        <Field label={t('prov.entity_kind')} value={proposal.entity_kind} mono />
        {model && <Field label={t('prov.model')} value={model} mono />}
      </div>

      {isRecook && (
        <div
          className="flex items-center gap-1.5 rounded-md border border-info/30 bg-info/5 px-2 py-1.5 text-[11px] text-info"
          data-testid="enrichment-prov-recook"
        >
          <ShieldCheck className="h-3.5 w-3.5 shrink-0" />
          {t('prov.recook_abstracted')}
        </div>
      )}

      {refs.length > 0 && (
        <div>
          <p className="mb-1 font-medium text-muted-foreground">{t('prov.grounding')}</p>
          <div className="space-y-1.5">
            {refs.map((r, i) => (
              <GroundingRow key={i} src={r} />
            ))}
          </div>
        </div>
      )}

      {skipped.length > 0 && (
        <div>
          <p className="mb-1 font-medium text-warning">{t('prov.skipped')}</p>
          <div className="space-y-1">
            {skipped.map((s, i) => (
              <SkippedRow key={i} src={s} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, value, mono }: { label: string; value: string | number; mono?: boolean }) {
  return (
    <div>
      <span className="text-muted-foreground">{label}: </span>
      <span className={mono ? 'font-mono' : undefined}>{String(value)}</span>
    </div>
  );
}

function LicenseTag({ license }: { license?: string }) {
  const { t } = useTranslation('enrichment');
  if (!license) return null;
  const ok = isRecookable(license);
  return (
    <span
      className={cn(
        'rounded-full px-1.5 py-0.5 text-[10px] font-medium',
        ok ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive',
      )}
    >
      {t(`license.${license}`, { defaultValue: license })}
    </span>
  );
}

function GroundingRow({ src }: { src: SourceRef }) {
  return (
    <div className="rounded-md border bg-card px-3 py-1.5">
      <div className="flex items-center gap-2">
        <span className="font-mono text-[11px] text-muted-foreground">
          {src.locator ?? src.corpus_id ?? '—'}
        </span>
        <LicenseTag license={src.license} />
        {typeof src.score === 'number' && (
          <span className="ml-auto font-mono text-[10px] text-muted-foreground">
            {src.score.toFixed(3)}
          </span>
        )}
      </div>
      {src.excerpt && (
        <p className="mt-1 line-clamp-2 font-serif text-[12px] text-foreground/80">{src.excerpt}</p>
      )}
    </div>
  );
}

function SkippedRow({ src }: { src: SkippedSource }) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-warning/20 bg-warning/5 px-2 py-1">
      <span className="font-mono text-[11px]">{src.name ?? src.corpus_id ?? '—'}</span>
      <LicenseTag license={src.license} />
      {src.reason && <span className="text-[10px] text-muted-foreground">{src.reason}</span>}
    </div>
  );
}
