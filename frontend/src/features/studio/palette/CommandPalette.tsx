// #06b Command Palette (⌘⇧P) — runs studio actions: switch view, toggle chrome, open a dock
// tool. Commands = static chrome (View: …) + one per registered dock tool (Panels group, empty
// until panels register). Empty query surfaces a Recent group (last 5 run). Reuses StudioPaletteShell.
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useRegisteredTools } from '../host/StudioHostProvider';
import type { ActivityView } from '../types';
import { StudioPaletteShell } from './StudioPaletteShell';
import { buildStudioCommands, filterCommands, type StudioCommand } from './useStudioCommands';
import type { PaletteEntry } from './types';

interface Props {
  open: boolean;
  onClose: () => void;
  chrome: {
    setActiveView: (v: ActivityView) => void;
    toggleSidebar: () => void;
    toggleBottom: () => void;
  };
  onOpenQuickOpen: () => void;
  onOpenPanel: (panelId: string) => void;
}

const RECENT_MAX = 5;
const RECENT_PREFIX = 'recent:';

const toEntry = (c: StudioCommand, idPrefix = ''): PaletteEntry => ({
  id: `${idPrefix}${c.id}`, label: c.label, sublabel: c.description, group: c.group,
});

export function CommandPalette({ open, onClose, chrome, onOpenQuickOpen, onOpenPanel }: Props) {
  const { t } = useTranslation('studio');
  const [query, setQuery] = useState('');
  const [recentIds, setRecentIds] = useState<string[]>([]);
  const tools = useRegisteredTools();

  useEffect(() => { if (open) setQuery(''); }, [open]);

  const commands = useMemo(
    () => buildStudioCommands({ chrome, tools, onOpenPanel, onOpenQuickOpen, t }),
    [chrome, tools, onOpenPanel, onOpenQuickOpen, t],
  );

  const entries: PaletteEntry[] = useMemo(() => {
    if (query.trim()) {
      return filterCommands(commands, query).map((c) => toEntry(c));
    }
    // Empty query → a Recent group (last-run, resolved against the live command set) on top of
    // the full grouped list. Recent entries carry a prefixed id so they don't collide with the
    // same command in its own group.
    const recentGroup = t('palette.group.recent', { defaultValue: 'Recent' });
    const recent = recentIds
      .map((id) => commands.find((c) => c.id === id))
      .filter((c): c is StudioCommand => !!c)
      .map((c) => ({ ...toEntry(c, RECENT_PREFIX), group: recentGroup }));
    return [...recent, ...commands.map((c) => toEntry(c))];
  }, [commands, query, recentIds, t]);

  const onSelect = (e: PaletteEntry) => {
    const id = e.id.startsWith(RECENT_PREFIX) ? e.id.slice(RECENT_PREFIX.length) : e.id;
    const command = commands.find((c) => c.id === id);
    if (command) {
      setRecentIds((prev) => [id, ...prev.filter((x) => x !== id)].slice(0, RECENT_MAX));
      command.run();
    }
    onClose();
  };

  return (
    <StudioPaletteShell
      open={open}
      onClose={onClose}
      query={query}
      onQueryChange={setQuery}
      placeholder={t('palette.commandPlaceholder', { defaultValue: 'Type a command…' })}
      entries={entries}
      onSelect={onSelect}
      emptyText={t('palette.noCommands', { defaultValue: 'No matching commands.' })}
      testid="command-palette"
    />
  );
}
