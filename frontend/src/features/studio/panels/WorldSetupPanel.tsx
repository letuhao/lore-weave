// The `world-setup` dock panel — the GUI for the deterministic glossary-build
// pipeline (spec docs/specs/2026-07-27-glossary-kg-build-workflows.md).
//
// Why it exists: the Mị Đế dogfood proved a weak model cannot reliably CHOOSE
// per-entity tools for world building. This panel drives the server-side FSM
// instead, with the human approving the plan and the relationships.
import type { IDockviewPanelProps } from 'dockview-react';

import { useUserModels } from '@/components/model-picker';
import { useAuth } from '@/auth';
import { WorldSetupWizard } from '@/features/world-setup/components/WorldSetupWizard';

import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function WorldSetupPanel(props: IDockviewPanelProps) {
  useStudioPanel('world-setup', props.api, { mcpToolPrefixes: ['composition_glossary_build'] });
  const host = useStudioHost();
  const { accessToken } = useAuth();
  // BYOK chat model — the run params carry the user_model UUID; provider-registry
  // resolves the actual model (never a literal name on this side).
  const models = useUserModels({ capability: 'chat' }).models;
  const modelRef = models?.[0]?.user_model_id ?? null;

  return (
    <div data-testid="studio-world-setup-panel" className="h-full min-h-0 overflow-auto">
      <WorldSetupWizard bookId={host.bookId} token={accessToken} modelRef={modelRef} />
    </div>
  );
}
