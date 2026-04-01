import type { AttrFieldProps } from './AttrTextCard';

export function AttrTextareaCard({ value, onChange }: AttrFieldProps) {
  return (
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      rows={3}
      className="w-full rounded-md border bg-background px-3 py-2 text-[13px] leading-relaxed resize-y focus:border-ring focus:outline-none focus:ring-[3px] focus:ring-ring/15 transition-all"
      style={{ minHeight: 72 }}
    />
  );
}
