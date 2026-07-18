// DF2 — the mobile assistant's greeting header (draft: "Good afternoon, Hao · Assistant" + the
// people/projects just noticed). A slim strip above the chat. The "noticed" chips come from the
// SHARED capture rail (context) so there's no extra fetch. View only.
import { User, Folder } from 'lucide-react';
import { useAuth } from '@/auth';
import { useAssistant } from '../../context/AssistantContext';

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
}

// Which glossary kinds render as a "person" chip vs a "project/thing" chip.
const PERSON_KINDS = new Set(['colleague', 'person', 'org']);

export function MobileAssistantHeader() {
  const { user } = useAuth();
  const { captureRail } = useAssistant();
  const name = (user?.display_name || user?.email || '').split(/[ @]/)[0];
  const chips = captureRail.entities.slice(0, 4);

  return (
    <div className="flex flex-col gap-1.5 border-b border-border bg-background px-3 py-2" data-testid="assistant-mobile-header">
      <div className="flex items-baseline justify-between">
        <span className="font-serif text-sm font-semibold">
          {greeting()}{name ? `, ${name}` : ''}
        </span>
        <span className="text-[11px] uppercase tracking-wide text-muted-foreground">Assistant</span>
      </div>
      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5" data-testid="assistant-noticed-strip">
          <span className="text-[11px] text-muted-foreground">Noticed</span>
          {chips.map((e) => {
            const person = PERSON_KINDS.has(e.kind?.code ?? '');
            const Icon = person ? User : Folder;
            return (
              <span
                key={e.entity_id}
                className="inline-flex items-center gap-1 rounded-full border border-border bg-card px-2 py-0.5 text-[11px]"
              >
                <Icon className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
                <span className="max-w-[7rem] truncate">{e.display_name}</span>
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
