type Visibility = 'private' | 'unlisted' | 'public';

const classByVisibility: Record<Visibility, string> = {
  private: 'border-slate-300 bg-slate-100 text-slate-700',
  unlisted: 'border-amber-300 bg-amber-100 text-amber-800',
  public: 'border-emerald-300 bg-emerald-100 text-emerald-800',
};

export function VisibilityBadge({ visibility }: { visibility?: Visibility }) {
  const safeVisibility: Visibility = visibility || 'private';
  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${classByVisibility[safeVisibility]}`}>
      {safeVisibility}
    </span>
  );
}
