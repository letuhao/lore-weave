import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ConfirmDialog } from '@/components/shared';
import { TechniqueBadge, VerifyBadge, ReviewStatusBadge, H0Marker } from './badges';
import { DimensionList } from './DimensionList';
import { VerifyPanel } from './VerifyPanel';
import { ProvenancePanel } from './ProvenancePanel';
import { ProposalActionBar } from './ProposalActionBar';
import { PromoteDialog } from './PromoteDialog';
import type { Proposal } from '../types';

/** Actions surface provided by useProposalActions (the controller). */
interface ProposalActions {
  busy: boolean;
  approve: (p: Proposal) => Promise<unknown>;
  reject: (p: Proposal, reason?: string) => Promise<unknown>;
  edit: (p: Proposal, content: string) => Promise<unknown>;
  promote: (p: Proposal) => Promise<unknown>;
  retract: (p: Proposal) => Promise<unknown>;
}

/** The full draft: H0 header + dimensions (editable) + verify (③/C12) + provenance
 *  (©) + the sticky ④ action bar. The parent keys this by proposal id, so selecting
 *  another proposal remounts it (drops any in-progress edit). */
export function ProposalDetail({ proposal, actions }: { proposal: Proposal; actions: ProposalActions }) {
  const { t } = useTranslation('enrichment');
  const [promoteOpen, setPromoteOpen] = useState(false);
  const [retractOpen, setRetractOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(proposal.content);

  const name = proposal.canonical_name || proposal.target_ref || t('untitled');
  const verify = proposal.provenance_json?.canon_verify;
  const verifyStatus = proposal.provenance_json?.verify_status;

  return (
    <div className="flex h-full flex-col" data-testid="enrichment-detail">
      <div className="flex-1 space-y-5 overflow-y-auto p-5">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-serif text-xl font-semibold" data-testid="enrichment-detail-name">{name}</h2>
            <TechniqueBadge technique={proposal.technique} />
            <ReviewStatusBadge status={proposal.review_status} />
            <VerifyBadge status={verifyStatus} />
            <H0Marker />
          </div>
          <div
            className="mt-2 rounded-md border border-warning/30 bg-warning/5 px-3 py-2"
            data-testid="enrichment-h0-banner"
          >
            <p className="text-xs font-medium text-warning">{t('detail.h0_banner')}</p>
            <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
              origin={proposal.origin} · confidence={proposal.confidence.toFixed(2)} ·{' '}
              {t(`review.${proposal.review_status}`, { defaultValue: proposal.review_status })}
            </p>
          </div>
        </div>

        <Section title={t('detail.content')}>
          {editing ? (
            <div className="space-y-2">
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                rows={10}
                className="w-full rounded-md border bg-background p-2 font-serif text-sm focus:outline-none focus:ring-2 focus:ring-ring/40"
              />
              <div className="flex gap-2">
                <button
                  onClick={async () => {
                    await actions.edit(proposal, draft);
                    setEditing(false);
                  }}
                  disabled={actions.busy}
                  className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
                >
                  {t('actions.save')}
                </button>
                <button
                  onClick={() => {
                    setDraft(proposal.content);
                    setEditing(false);
                  }}
                  className="rounded-md border px-3 py-1.5 text-xs text-muted-foreground hover:bg-secondary"
                >
                  {t('actions.cancel')}
                </button>
              </div>
            </div>
          ) : (
            <DimensionList proposal={proposal} />
          )}
        </Section>

        <Section title={t('detail.verify')}>
          <VerifyPanel verify={verify} />
        </Section>

        <Section title={t('detail.provenance')}>
          <ProvenancePanel proposal={proposal} />
        </Section>
      </div>

      <div className="border-t bg-background/80 p-4 backdrop-blur">
        <ProposalActionBar
          proposal={proposal}
          busy={actions.busy}
          onPromote={() => setPromoteOpen(true)}
          onApprove={() => void actions.approve(proposal)}
          onReject={(reason) => void actions.reject(proposal, reason)}
          onRetract={() => setRetractOpen(true)}
          onEdit={() => {
            setDraft(proposal.content);
            setEditing(true);
          }}
        />
        <p className="mt-2 text-right text-[10px] text-muted-foreground">{t('actions.author_only')}</p>
      </div>

      <PromoteDialog
        proposal={proposal}
        open={promoteOpen}
        onOpenChange={setPromoteOpen}
        busy={actions.busy}
        onConfirm={async () => {
          await actions.promote(proposal);
          setPromoteOpen(false);
        }}
      />

      <ConfirmDialog
        open={retractOpen}
        onOpenChange={setRetractOpen}
        variant="destructive"
        title={t('actions.retract_confirm_title')}
        description={t('actions.retract_confirm_desc')}
        confirmLabel={t('actions.retract')}
        cancelLabel={t('actions.cancel')}
        loading={actions.busy}
        onConfirm={async () => {
          await actions.retract(proposal);
          setRetractOpen(false);
        }}
      />
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </h3>
      {children}
    </div>
  );
}
