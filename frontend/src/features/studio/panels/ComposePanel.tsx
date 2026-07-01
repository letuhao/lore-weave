// #03 Compose — the first STATEFUL studio dock panel: the AI co-writer chat, embedded.
//
// Reuses the whole chat feature AS-IS (Chat.tsx — the reusable surface with rack #07a + inspector
// #07b already wired in ChatView). No fork. The panel is a thin host that:
//   • reads bookId from the StudioHost (per-book studio session),
//   • registers itself for the AGENT rack (#07a — mcp prefixes / skills this surface owns),
//   • renders <Chat windowingEnabled> so an in-flight turn runs in the SharedWorker and SURVIVES a
//     dock float / close / pop-out (D4 turn-survival without a separate hoist).
import { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { Chat } from '@/features/chat/Chat';
import { useStudioHost, useRegisterStudioTool } from '../host/StudioHostProvider';
import { StudioAgentBridge } from '../agent/StudioAgentBridge';
import type { StudioToolRegistration } from '../host/types';

export function ComposePanel(props: IDockviewPanelProps) {
  const { t } = useTranslation('studio');
  const { bookId } = useStudioHost();

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

  return (
    <div data-testid="studio-compose-panel" className="h-full min-h-0">
      {/* The agent↔GUI bridge (Lane A/B #09) rides the actionBar slot — Chat renders it INSIDE its
          providers, so it reads the live chat stream (useChatStream). It renders nothing visible.
          studioContext (presence) makes chat-service advertise the studio dock-nav tools (Lane A). */}
      <Chat
        bookId={bookId}
        studioContext={{ book_id: bookId }}
        windowingEnabled
        actionBar={<StudioAgentBridge />}
        className="h-full"
      />
    </div>
  );
}
