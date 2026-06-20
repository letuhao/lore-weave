type StatusBannerProps = {
  status: { kind: 'ok' | 'err'; text: string } | null;
  onDismiss: () => void;
};

export function StatusBanner({ status, onDismiss }: StatusBannerProps) {
  if (!status) return null;
  const ok = status.kind === 'ok';
  return (
    <div
      role="status"
      className={`flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm ${
        ok
          ? 'border-border bg-secondary/40 text-foreground'
          : 'border-destructive/40 bg-destructive/10 text-destructive'
      }`}
    >
      <span>{status.text}</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="text-xs underline opacity-70 hover:opacity-100"
      >
        dismiss
      </button>
    </div>
  );
}
