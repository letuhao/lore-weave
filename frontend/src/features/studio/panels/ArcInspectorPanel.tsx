// 32 arc-inspector — the dock panel (category `editor`). Palette-openable by BARE ID (AI-1): the
// subject resolves props.params.arcId -> bus.activeArcId -> this in-panel picker, so an agent/palette
// open is never a dead panel. Chrome + picker live here; the SHARED body (also embedded in
// PlanDrawer, AI-4/DOCK-2) renders the sections. Logic is in useArcInspector.
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';

import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { useArcInspector, type ArcFocusParams } from './useArcInspector';
import { ArcInspectorBody } from './ArcInspectorBody';

export function ArcInspectorPanel(props: IDockviewPanelProps) {
  useStudioPanel('arc-inspector', props.api);
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const params = props.params as ArcFocusParams | undefined;
  const state = useArcInspector(host.bookId, params?.arcId);
  const { shell, arcId, detail } = state;

  const emptyBook = !state.loading && shell.length === 0;

  return (
    <div data-testid="studio-arc-inspector-panel" className="flex h-full min-h-0 flex-col text-sm">
      {/* Subject picker (shell tree, indented by depth). Always live, even while the body loads. */}
      <div className="flex flex-col gap-1.5 border-b p-2">
        <select
          data-testid="arc-inspector-picker"
          className="w-full rounded border bg-background px-2 py-1 text-xs"
          value={arcId ?? ''}
          onChange={(e) => state.select(e.target.value || null)}
        >
          <option value="">{t('panels.arc-inspector.pick', { defaultValue: 'Select an arc…' })}</option>
          {shell.map((n) => (
            <option key={n.id} value={n.id}>
              {`${'  '.repeat(Math.max(0, n.depth))}${n.kind === 'saga' ? '§ ' : ''}${n.title || '(untitled)'}`}
            </option>
          ))}
        </select>
        {detail && (
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
            <span className="uppercase tracking-wide">{detail.kind}</span>
            <span className="font-mono">v{detail.version}</span>
          </div>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {emptyBook ? (
          <div data-testid="arc-inspector-empty-book" className="flex flex-col items-center gap-3 p-6 text-center">
            <p className="max-w-xs text-xs text-muted-foreground">
              {t('panels.arc-inspector.emptyBook', {
                defaultValue: 'No arcs yet — the spec tree is what steers generation. Extract a plan from the manuscript in the Plan Hub, or create an arc there.',
              })}
            </p>
            <button
              type="button"
              data-testid="arc-inspector-open-hub"
              className="rounded border border-border bg-background px-3 py-1 text-xs font-semibold hover:border-ring"
              onClick={() => host.openPanel('plan-hub', { focus: true })}
            >
              {t('panels.arc-inspector.openHub', { defaultValue: 'Open the Plan Hub' })}
            </button>
          </div>
        ) : (
          <ArcInspectorBody
            state={state}
            onOpenPromise={() => host.openPanel('quality-promises', { focus: true })}
          />
        )}
      </div>
    </div>
  );
}
