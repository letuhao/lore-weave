// #09 Lane A — resolve a studio `ui_*` frontend tool into a host side-effect + the resume payload
// the agent reads back. Pure (no React, no host in the signature — returns an `effect` closure the
// executor runs with the live host), so it's unit-testable on its own.
//
// These suspend→browser like propose_edit but RESOLVE IMMEDIATELY (no human Apply gate): the agent
// asked to move the studio UI, the FE just does it. Args carry IDs ONLY — never prose/draft blobs
// (G2: no data-bearing frontend tools).
import type { StudioHost } from '../host/StudioHostProvider';

export const STUDIO_UI_TOOLS = ['ui_open_studio_panel', 'ui_focus_manuscript_unit'] as const;
export type StudioUiToolName = (typeof STUDIO_UI_TOOLS)[number];

export function isStudioUiTool(name: string): name is StudioUiToolName {
  return (STUDIO_UI_TOOLS as readonly string[]).includes(name);
}

export interface StudioUiResolution {
  /** resume payload POSTed back to the agent (always reflects whether the action was performed) */
  result: Record<string, unknown>;
  /** the side-effect to run against the live host (absent when the request was rejected) */
  effect?: (host: StudioHost) => void;
}

export function resolveStudioUiTool(tool: string, args: Record<string, unknown>): StudioUiResolution {
  switch (tool) {
    case 'ui_open_studio_panel': {
      const panelId = typeof args.panel_id === 'string' ? args.panel_id : '';
      if (!panelId) return { result: { opened: false } };
      return { result: { opened: true }, effect: (host) => host.openPanel(panelId) };
    }
    case 'ui_focus_manuscript_unit': {
      const chapterId = typeof args.chapter_id === 'string' ? args.chapter_id : '';
      if (!chapterId) return { result: { focused: false } };
      return { result: { focused: true }, effect: (host) => host.focusManuscriptUnit(chapterId) };
    }
    default:
      return { result: {} };
  }
}
