import { useTranslation } from 'react-i18next';
import { groupToolsByServer } from '../utils/serverKey';

// W6 — the AgentContextRack's tool chips, grouped by owning MCP server.
// Each group renders a small section label (server name · count) with a status
// dot: green when the live agentSurface frame's `servers` map covers the key
// (the backend derived it from a successful catalog fetch this turn), muted
// when the names came from session pins only (no live catalog data).
// Pinned chips keep their remove ×; discovered chips are read-only (cleared
// via the rack's "Clear discovered" menu action).

const DISCOVERED_CHIP_CAP = 8;

interface RackServerGroupsProps {
  pinned: string[];
  discovered: string[];
  /** live per-server grouping from the last agentSurface frame (undefined
   *  or missing key → that server's tools are pins-only → muted dot). */
  liveServers?: Record<string, { tools: number }> | null;
  onRemoveTool: (name: string) => void;
  disabled?: boolean;
}

export function RackServerGroups({
  pinned,
  discovered,
  liveServers,
  onRemoveTool,
  disabled,
}: RackServerGroupsProps) {
  const { t } = useTranslation('chat');
  const pinnedSet = new Set(pinned);
  const discoveredOnly = discovered.filter((name) => !pinnedSet.has(name));
  const groups = groupToolsByServer([...pinned, ...discoveredOnly]);
  if (groups.length === 0) return null;

  return (
    <>
      {groups.map(({ key, tools }) => {
        const live = !!liveServers?.[key];
        // all pinned chips always render; discovered chips cap per group.
        const groupPinned = tools.filter((n) => pinnedSet.has(n));
        const groupDiscovered = tools.filter((n) => !pinnedSet.has(n));
        const shown = [...groupPinned, ...groupDiscovered.slice(0, DISCOVERED_CHIP_CAP)];
        const hidden = groupDiscovered.length - Math.min(groupDiscovered.length, DISCOVERED_CHIP_CAP);
        return (
          <span key={key} className="inline-flex flex-wrap items-center gap-1" data-testid={`agent-rack-server-${key}`}>
            <span
              className="inline-flex items-center gap-1 text-[10px] font-medium text-muted-foreground"
              title={live ? t('rack.server_live') : t('rack.server_pins_only')}
            >
              <span
                data-testid={`agent-rack-server-dot-${key}`}
                data-live={live ? '1' : '0'}
                className={`inline-block h-1.5 w-1.5 rounded-full ${live ? 'bg-emerald-500' : 'bg-muted-foreground/40'}`}
              />
              {t(`rack.server.${key}`, { defaultValue: key })} · {tools.length}
            </span>
            {shown.map((name) => {
              const isPinned = pinnedSet.has(name);
              return (
                <span
                  key={name}
                  data-testid={`agent-rack-chip-tool-${name}`}
                  className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] ${
                    isPinned ? 'border-border bg-background' : 'border-dashed border-border/70 bg-muted/40 text-muted-foreground'
                  }`}
                >
                  <span className="text-muted-foreground">🔧</span>
                  {name}
                  {isPinned && !disabled && (
                    <button
                      type="button"
                      onClick={() => onRemoveTool(name)}
                      className="text-muted-foreground hover:text-foreground"
                      aria-label={t('rack.remove')}
                    >
                      ×
                    </button>
                  )}
                </span>
              );
            })}
            {hidden > 0 && (
              <span
                className="text-[10px] text-muted-foreground"
                title={t('rack.more_tooltip', { count: hidden })}
              >
                {t('rack.more', { count: hidden })}
              </span>
            )}
          </span>
        );
      })}
    </>
  );
}
