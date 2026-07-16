// Studio Quality tab — `quality-canon-rules`: the WRITE half of `quality-canon`.
//
// `quality-canon` (shipped) says WHAT IS BROKEN — it merges three read lenses and has zero writes.
// This panel says WHAT THE RULES ARE: author the invariants the critic enforces (create · edit · archive
// · restore). Until it shipped, the Studio judged the author against canon rules and gave them no surface
// to write one — the complete CRUD (`CanonRulesPanel` + `CanonRuleForm` + `useCanonRules`) was mounted
// ONLY on the legacy ChapterEditorPage. This is a PORT: the component is reused as-is behind the shared
// `QualityWorkGate` (so a GUI-only user can `Set up co-writer` from here too, D0).
//
// The pair deep-links both directions by rule id (S6 spec §4): `quality-canon`'s "Edit rule" opens this
// panel focused; this panel's "N broken" opens `quality-canon` focused. (The focus param plumbing lands
// with the 412 / deep-link slice.)
import type { IDockviewPanelProps } from 'dockview-react';
import { useAuth } from '@/auth';
import { CanonRulesPanel } from '@/features/composition/components/CanonRulesPanel';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { QualityWorkGate } from './QualityNoWorkState';
import { useQualityWork } from './useQualityWork';

export function QualityCanonRulesPanel(props: IDockviewPanelProps) {
  useStudioPanel('quality-canon-rules', props.api);
  const host = useStudioHost();
  const { accessToken } = useAuth();
  // Authoring a rule is per-project (per composition Work), so it gates like the other quality panels —
  // and offers the Set-up-co-writer CTA on `no-work`. `unavailable` (composition-service down) is an
  // error, never the CTA (that would invite a duplicate Work). See useQualityWork / RUN-STATE DR-27.
  const work = useQualityWork(host.bookId, accessToken);

  if (work.kind !== 'ready') {
    return <QualityWorkGate state={work} testIdPrefix="quality-canon-rules" bookId={host.bookId} token={accessToken} />;
  }

  return (
    <div data-testid="studio-quality-canon-rules-panel" className="h-full min-h-0 overflow-auto">
      <CanonRulesPanel projectId={work.projectId} bookId={host.bookId} token={accessToken} />
    </div>
  );
}
