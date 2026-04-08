import { ChevronUp, ChevronDown } from 'lucide-react';

export function TrendArrow({ change }: { change: number }) {
  if (change > 0) {
    return (
      <span className="inline-flex items-center gap-0.5 text-[10px] text-green-400">
        <ChevronUp className="h-2.5 w-2.5" strokeWidth={3} />
        +{change}
      </span>
    );
  }
  if (change < 0) {
    return (
      <span className="inline-flex items-center gap-0.5 text-[10px] text-destructive">
        <ChevronDown className="h-2.5 w-2.5" strokeWidth={3} />
        {change}
      </span>
    );
  }
  return <span className="text-[10px] text-muted-foreground">&mdash;</span>;
}
