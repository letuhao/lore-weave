import { AlertTriangle } from 'lucide-react';
import { ConfirmDialog } from './ConfirmDialog';

interface UnsavedChangesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: () => void | Promise<void>;
  onDiscard: () => void;
  saving?: boolean;
}

export function UnsavedChangesDialog({
  open, onOpenChange, onSave, onDiscard, saving,
}: UnsavedChangesDialogProps) {
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Unsaved changes"
      description="You have changes that haven't been saved yet. What would you like to do before leaving?"
      icon={<AlertTriangle className="h-5 w-5 text-amber-500" />}
      extraAction={{ label: 'Save & leave', onClick: onSave, loading: saving }}
      confirmLabel="Discard & leave"
      cancelLabel="Stay on page"
      onConfirm={onDiscard}
    />
  );
}
