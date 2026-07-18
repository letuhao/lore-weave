// #03 Compose — the first STATEFUL studio dock panel: the AI co-writer chat, embedded.
//
// Reuses the whole chat feature AS-IS (Chat.tsx — the reusable surface with rack #07a + inspector
// #07b already wired in ChatView). No fork. The panel is a thin host that:
//   • reads bookId from the StudioHost (per-book studio session),
//   • registers itself for the AGENT rack (#07a — mcp prefixes / skills this surface owns),
//   • renders <Chat windowingEnabled> so an in-flight turn runs in the SharedWorker and SURVIVES a
//     dock float / close / pop-out (D4 turn-survival without a separate hoist).
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { Chat } from '@/features/chat/Chat';
import { UiNavInterceptorContext } from '@/features/chat/nav/uiNavScope';
import { PopoutBridge } from '@/features/composition/components/workspace/PopoutBridge';
import { useStudioHost, useRegisterStudioTool } from '../host/StudioHostProvider';
import { useManuscriptUnitMeta } from '../manuscript/unit/ManuscriptUnitProvider';
import { StudioAgentBridge } from '../agent/StudioAgentBridge';
import { makeStudioNavInterceptor } from '../agent/studioUiNav';
import type { StudioToolRegistration } from '../host/types';

export function ComposePanel(props: IDockviewPanelProps) {
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const { bookId } = host;
  // #12 M-E — remap same-book C-NAV tools to dock actions so an agent nav call can never
  // navigate the SPA out of the studio (which would unmount this very panel mid-run).
  const navInterceptor = useMemo(() => makeStudioNavInterceptor(host), [host]);
  // CTX-1 (M-E live-caught) — the position pointer. The agent knows the book_id but every
  // composition_* tool keys on project_id, and the model dead-ended trying to discover it
  // (retried the book_id AS a project_id → uniform deny → spin). The hoist already resolved
  // the Work — carry project_id + the active chapter in studio_context so chat-service can
  // TELL the model instead of making it forage. Meta context = stable slice (no per-keystroke
  // re-render of the chat subtree).
  const unitMeta = useManuscriptUnitMeta();
  const studioContext = useMemo(() => ({
    book_id: bookId,
    ...(unitMeta?.projectId ? { project_id: unitMeta.projectId } : {}),
    ...(unitMeta?.activeChapterId ? { active_chapter_id: unitMeta.activeChapterId } : {}),
  }), [bookId, unitMeta?.projectId, unitMeta?.activeChapterId]);
  // #09/APPLY-DIFF fix — EditorPanel already registers the propose_edit write-back target
  // (registerEditorTarget) whenever a chapter is open, but chat-service only advertises
  // propose_edit when `editor_context` is present (stream_service.py ~1924/1685). Without this,
  // the agent can never initiate a human-gated prose diff on the studio surface. Mirrors the
  // legacy ChapterEditorPage.tsx's `editorContext={{ book_id, chapter_id }}` exactly; omitted
  // (undefined) when no chapter is open yet, same as studioContext's active_chapter_id.
  const editorContext = useMemo(
    () => (unitMeta?.activeChapterId ? { book_id: bookId, chapter_id: unitMeta.activeChapterId } : undefined),
    [bookId, unitMeta?.activeChapterId],
  );

  // Register for the agent rack (#07a): this surface exposes the composition tool family + the
  // universal skill. Stable object (panelId keyed) so the registry never churns.
  const label = t('panels.compose.title', { defaultValue: 'Compose' });
  const registration = useMemo<StudioToolRegistration>(() => ({
    panelId: 'compose',
    label,
    paletteCommand: t('palette.openPanel', { name: label, defaultValue: 'Studio: Open Compose' }),
    commandId: 'studio.openPanel.compose',
    description: t('panels.compose.desc', { defaultValue: 'AI co-writer chat' }),
    mcpToolPrefixes: ['composition_'],
    skills: ['universal'],
  }), [t, label]);
  useRegisterStudioTool(registration);

  // Self-title the dock tab from the localized label (an agent-opened panel otherwise shows the raw
  // 'compose' id, since openPanel sets the title before this panel mounts). See EditorPanel.
  useEffect(() => {
    props.api.setTitle(label);
  }, [props.api, label]);

  // #16 2.8 — Pop out into a real OS/browser window (multi-monitor use). Dockview's own
  // float/split already covers "same-page window" — this is for a genuinely separate window,
  // reusing the composition workspace's window-lifecycle bridge (open/close-poll/dock-back)
  // via its generalized `route` prop instead of forking that logic. Gated on a chapter being
  // open: the popout's editor/studio context is chapter-scoped (mirrors editorContext above).
  const [poppedOut, setPoppedOut] = useState(false);
  const activeChapterId = unitMeta?.activeChapterId ?? null;
  const popoutTitle = t('popout.openTitle', { defaultValue: 'Open Compose in its own window' });
  // N7 — when the pop-out is disabled it's ALWAYS because no chapter is open (the popped window
  // is chapter-scoped). Say so, so a newcomer isn't left staring at a greyed button with no reason.
  const popoutDisabledTitle = t('popout.needChapter', {
    defaultValue: 'Open a chapter first — pop-out opens the current chapter in its own window',
  });

  return (
    <div data-testid="studio-compose-panel" className="flex h-full min-h-0 flex-col">
      <div className="flex h-7 flex-shrink-0 items-center justify-end border-b px-2 text-[11px] text-muted-foreground">
        <button
          type="button"
          data-testid="studio-compose-popout"
          title={!activeChapterId ? popoutDisabledTitle : popoutTitle}
          disabled={!activeChapterId || poppedOut}
          onClick={() => setPoppedOut(true)}
          className="rounded px-1.5 py-0.5 hover:bg-secondary hover:text-foreground disabled:opacity-40"
        >
          ⤢ {t('popout.open', { defaultValue: 'Pop out' })}
        </button>
      </div>
      {/* The agent↔GUI bridge (Lane A/B #09) rides the actionBar slot — Chat renders it INSIDE its
          providers, so it reads the live chat stream (useChatStream). It renders nothing visible.
          studioContext (presence) makes chat-service advertise the studio dock-nav tools (Lane A). */}
      <div className="min-h-0 flex-1">
        <UiNavInterceptorContext.Provider value={navInterceptor}>
          <Chat
            bookId={bookId}
            editorContext={editorContext}
            studioContext={studioContext}
            windowingEnabled
            actionBar={<StudioAgentBridge />}
            className="h-full"
          />
        </UiNavInterceptorContext.Provider>
      </div>
      {poppedOut && activeChapterId && (
        <PopoutBridge
          id="compose"
          bookId={bookId}
          chapterId={activeChapterId}
          route="/studio/popout"
          onClosed={() => setPoppedOut(false)}
        />
      )}
    </div>
  );
}
