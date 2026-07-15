// Presentational binding settings (M6) — render-only; data + actions via props (MVC).
// For each mode it shows the EFFECTIVE injected workflows, each tagged with the TIER it came from
// (Settings & Config SET-1: effective value + source, never a silent hidden default), and lets the
// user VETO a System pin (toggle it off) — the affordance that makes this a real per-user setting.
import type { Mode, ModeBinding, Tier } from '../types';
import { MODES } from '../types';

const MODE_LABEL: Record<Mode, string> = {
  ask: 'Reading & asking',
  write: 'Writing',
  plan: 'Planning',
};
const TIER_LABEL: Record<Tier, string> = { system: 'Built-in', user: 'You set this', book: 'This book' };

export interface BindingSettingsProps {
  bindings: Record<Mode, ModeBinding | null>;
  loading: boolean;
  error: string | null;
  busyMode: Mode | null;
  onToggleDisabled: (mode: Mode, slug: string, disabled: boolean) => void;
}

/** Which tier contributed a given workflow slug (for the source badge). */
function sourceOf(b: ModeBinding, slug: string): Tier {
  const src = b.sources ?? {};
  for (const tier of ['book', 'user', 'system'] as Tier[]) {
    if (src[tier]?.inject_workflows?.includes(slug)) return tier;
  }
  return 'system';
}

export function BindingSettings({ bindings, loading, error, busyMode, onToggleDisabled }: BindingSettingsProps) {
  if (loading) return <div className="p-4 text-sm text-muted-foreground" data-testid="bindings-loading">Loading…</div>;
  if (error) return <div className="p-4 text-sm text-destructive" role="alert" data-testid="bindings-error">{error}</div>;

  return (
    <div className="flex flex-col gap-5 p-3" data-testid="binding-settings">
      {MODES.map((mode) => {
        const b = bindings[mode];
        if (!b) return null;
        const effective = b.inject_workflows ?? [];
        const vetoed = b.disable_workflows ?? [];
        return (
          <section key={mode} aria-label={MODE_LABEL[mode]}>
            <h3 className="mb-1 text-sm font-semibold text-foreground">{MODE_LABEL[mode]}</h3>
            <p className="mb-2 text-xs text-muted-foreground">
              Recipes the assistant sets up automatically in this mode.
            </p>

            {effective.length === 0 && vetoed.length === 0 && (
              <div className="text-xs text-muted-foreground" data-testid={`bindings-${mode}-none`}>
                Nothing is auto-set-up here.
              </div>
            )}

            <ul className="flex flex-col gap-1">
              {effective.map((slug) => {
                const tier = sourceOf(b, slug);
                return (
                  <li key={slug} className="flex items-center justify-between rounded-md border border-border px-3 py-1.5" data-testid={`binding-${mode}-${slug}`}>
                    <span className="text-sm text-foreground">
                      {slug}
                      <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                        {TIER_LABEL[tier]}
                      </span>
                    </span>
                    <button
                      type="button"
                      disabled={busyMode === mode}
                      onClick={() => onToggleDisabled(mode, slug, true)}
                      className="text-xs text-muted-foreground hover:text-destructive disabled:opacity-50"
                      data-testid={`binding-${mode}-${slug}-disable`}
                    >
                      Turn off
                    </button>
                  </li>
                );
              })}
              {vetoed.map((slug) => (
                <li key={`off-${slug}`} className="flex items-center justify-between rounded-md border border-dashed border-border px-3 py-1.5 opacity-70" data-testid={`binding-${mode}-${slug}-off`}>
                  <span className="text-sm text-muted-foreground line-through">{slug}</span>
                  <button
                    type="button"
                    disabled={busyMode === mode}
                    onClick={() => onToggleDisabled(mode, slug, false)}
                    className="text-xs text-primary hover:underline disabled:opacity-50"
                    data-testid={`binding-${mode}-${slug}-enable`}
                  >
                    Turn back on
                  </button>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
