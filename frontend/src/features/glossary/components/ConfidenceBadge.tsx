import type { Confidence } from '../types';

const CONFIG: Record<Confidence, { label: string; className: string }> = {
  verified: { label: 'Verified', className: 'border-green-200 bg-green-100 text-green-800' },
  draft: { label: 'Draft', className: 'border-yellow-200 bg-yellow-100 text-yellow-800' },
  machine: { label: 'Machine', className: 'border-blue-200 bg-blue-100 text-blue-800' },
};

type Props = { confidence: Confidence };

export function ConfidenceBadge({ confidence }: Props) {
  const { label, className } = CONFIG[confidence] ?? CONFIG.draft;
  return (
    <span
      className={`inline-flex items-center rounded-full border px-1.5 py-0.5 text-xs font-medium ${className}`}
    >
      {label}
    </span>
  );
}
