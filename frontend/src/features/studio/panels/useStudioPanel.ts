// Shared dock-panel chrome (#11 checklist items 3+5): register with the studio host for the
// palette/agent rack, and self-title the dock tab from the localized label (openPanel sets the
// title at addPanel time, BEFORE the panel mounts — an agent/resolver open without a title opt
// shows the raw id until the panel claims it here; also keeps titles correct across locale swaps).
import { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { useRegisterStudioTool } from '../host/StudioHostProvider';
import type { StudioToolRegistration } from '../host/types';

export function useStudioPanel(
  panelId: string,
  api: IDockviewPanelProps['api'],
  extras?: Pick<StudioToolRegistration, 'mcpToolPrefixes' | 'mcpTools' | 'frontendTools' | 'skills'>,
): string {
  const { t } = useTranslation('studio');
  const label = t(`panels.${panelId}.title`, { defaultValue: panelId });

  const registration = useMemo<StudioToolRegistration>(() => ({
    panelId,
    label,
    paletteCommand: t('palette.openPanel', { name: label, defaultValue: `Studio: Open ${label}` }),
    commandId: `studio.openPanel.${panelId}`,
    description: t(`panels.${panelId}.desc`, { defaultValue: '' }) || undefined,
    ...extras,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [t, label, panelId]);
  useRegisterStudioTool(registration);

  useEffect(() => {
    api.setTitle(label);
  }, [api, label]);

  return label;
}
