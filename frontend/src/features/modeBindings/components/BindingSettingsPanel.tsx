// Container for the binding settings (M6): wires useModeBindings to the presentational component.
import { useModeBindings } from '../hooks/useModeBindings';
import { BindingSettings } from './BindingSettings';

export interface BindingSettingsPanelProps {
  bookId?: string;
}

export function BindingSettingsPanel({ bookId }: BindingSettingsPanelProps) {
  const { bindings, loading, error, busyMode, setWorkflowDisabled } = useModeBindings(bookId);
  return (
    <BindingSettings
      bindings={bindings}
      loading={loading}
      error={error}
      busyMode={busyMode}
      onToggleDisabled={setWorkflowDisabled}
    />
  );
}
