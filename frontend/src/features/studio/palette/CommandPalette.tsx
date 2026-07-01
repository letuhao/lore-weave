// #06b Command Palette (⌘⇧P) — runs studio actions: switch view, toggle chrome, open a dock
// tool. Commands = static chrome (View: …) + one per registered dock tool (Panels group, empty
// until panels register). Reuses StudioPaletteShell.
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useRegisteredTools } from '../host/StudioHostProvider';
import type { ActivityView } from '../types';
import { StudioPaletteShell } from './StudioPaletteShell';
import { buildStudioCommands, filterCommands } from './useStudioCommands';
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

export function CommandPalette({ open, onClose, chrome, onOpenQuickOpen, onOpenPanel }: Props) {
  const { t } = useTranslation('studio');
  const [query, setQuery] = useState('');
  const tools = useRegisteredTools();

  // Fresh query each time the palette opens.
  useEffect(() => { if (open) setQuery(''); }, [open]);

  const commands = useMemo(
    () => buildStudioCommands({ chrome, tools, onOpenPanel, onOpenQuickOpen, t }),
    [chrome, tools, onOpenPanel, onOpenQuickOpen, t],
  );
  const filtered = useMemo(() => filterCommands(commands, query), [commands, query]);
  const entries: PaletteEntry[] = filtered.map((c) => ({ id: c.id, label: c.label, group: c.group }));

  const onSelect = (e: PaletteEntry) => {
    filtered.find((c) => c.id === e.id)?.run();
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
