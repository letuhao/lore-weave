// View: the footerSlot bar injected into the reused ChatView. One action —
// end the interview and produce a scorecard. Render only.

import { ClipboardCheck, Loader2 } from 'lucide-react';

interface EndEvaluateBarProps {
  evaluating: boolean;
  onEvaluate: () => void;
}

export function EndEvaluateBar({ evaluating, onEvaluate }: EndEvaluateBarProps) {
  return (
    <div className="flex items-center justify-between gap-3 border-t bg-muted/30 px-4 py-2">
      <span className="text-xs text-muted-foreground">Done? End the interview to get your scorecard.</span>
      <button
        type="button"
        disabled={evaluating}
        onClick={onEvaluate}
        className="flex items-center gap-1.5 rounded-md border border-primary/40 px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/10 disabled:opacity-50"
      >
        {evaluating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ClipboardCheck className="h-3.5 w-3.5" />}
        End &amp; evaluate
      </button>
    </div>
  );
}
