import { useState } from 'react';

/** Manages open/close state for side panels in ChatView. */
export function usePanelState() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [voiceSettingsOpen, setVoiceSettingsOpen] = useState(false);

  return { settingsOpen, setSettingsOpen, voiceSettingsOpen, setVoiceSettingsOpen };
}
