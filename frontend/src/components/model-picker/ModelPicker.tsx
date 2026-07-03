import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ChevronsUpDown,
  Globe,
  Image,
  ListOrdered,
  Layers,
  MessageSquare,
  Mic,
  Search,
  Shield,
  Star,
  Video,
  Volume2,
  Wrench,
} from 'lucide-react';
import { useAuth } from '@/auth';
import { aiModelsApi, getUserModelMeta, type UserModel } from '@/features/ai-models/api';
import { AddModelCta } from '@/components/shared/AddModelCta';
import { cn } from '@/lib/utils';
import { useUserModels, invalidateUserModelsCache } from './useUserModels';
import { loadRecentsCached, loadRecentsFromServer, pushRecent } from './recents';

/**
 * W5 — THE shared model picker. Every model-selection surface renders this
 * (directly or via a thin site wrapper) instead of a bespoke fetch + <select>.
 *
 * Features: search (alias / model name / provider), favorites pinned on top
 * (star toggle per row via the existing PATCH favorite route, optimistic),
 * recents (last-5 per capability via /v1/me/preferences), grouping by
 * provider_kind, per-row badges (context length, capability icons, "$0 local"
 * / "$" pricing hint), combobox/listbox semantics with keyboard navigation.
 *
 * Fetch defaults: active-only + the passed capability (server-side filter —
 * undeclared `{}` local models count as chat-capable for capability="chat").
 */
export interface ModelPickerProps {
  /** Server-side capability filter (chat / embedding / rerank / tts / …). */
  capability?: string;
  /** Selected user_model_id, or null. */
  value: string | null;
  onChange: (userModelId: string | null) => void;
  /** Offer an explicit "none" choice (emits null). */
  allowNone?: boolean;
  /** Label for the none choice (defaults to modelPicker.none). */
  noneLabel?: string;
  /** Trigger text when nothing is selected. */
  placeholder?: string;
  disabled?: boolean;
  /** Smaller trigger for dense surfaces (toolbars). */
  compact?: boolean;
  /** Accessible name for the combobox trigger. */
  ariaLabel?: string;
  /** Include deactivated models (default false). */
  includeInactive?: boolean;
  /** Replace the default zero-models state (message + AddModelCta). */
  emptyState?: ReactNode;
  className?: string;
}

const CAPABILITY_ICONS: Record<string, typeof MessageSquare> = {
  chat: MessageSquare,
  embedding: Layers,
  rerank: ListOrdered,
  tts: Volume2,
  stt: Mic,
  image_gen: Image,
  video_gen: Video,
  tool_calling: Wrench,
  moderation: Shield,
  web_search: Globe,
};

type Option = {
  id: string; // '' = the none option
  model?: UserModel;
  orphan?: boolean;
};

export function ModelPicker({
  capability,
  value,
  onChange,
  allowNone,
  noneLabel,
  placeholder,
  disabled,
  compact,
  ariaLabel,
  includeInactive,
  emptyState,
  className,
}: ModelPickerProps) {
  const { t } = useTranslation('common');
  const { accessToken, user } = useAuth();
  const userId = user?.user_id;
  const { models, loading, error, mutate } = useUserModels({ capability, includeInactive });

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [recents, setRecents] = useState<string[]>(() => loadRecentsCached(capability, userId));

  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const listboxId = useId();

  // Refresh recents from the server (multi-device) once per capability/user.
  useEffect(() => {
    let cancelled = false;
    setRecents(loadRecentsCached(capability, userId));
    void loadRecentsFromServer(capability, accessToken, userId).then((serverRecents) => {
      if (!cancelled && serverRecents) setRecents(serverRecents);
    });
    return () => {
      cancelled = true;
    };
  }, [capability, accessToken, userId]);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    function onMouseDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    window.addEventListener('mousedown', onMouseDown);
    return () => window.removeEventListener('mousedown', onMouseDown);
  }, [open]);

  // Focus the search box when the popup opens.
  useEffect(() => {
    if (open) {
      setQuery('');
      setActiveIndex(0);
      const timer = setTimeout(() => searchRef.current?.focus(), 0);
      return () => clearTimeout(timer);
    }
  }, [open]);

  // ── Derived option sections ────────────────────────────────────────────────
  const { sections, flatOptions, selectedModel, orphan } = useMemo(() => {
    const all = models ?? [];
    const q = query.trim().toLowerCase();
    const matches = (m: UserModel) => {
      if (!q) return true;
      const meta = getUserModelMeta(m);
      return (
        meta.displayName.toLowerCase().includes(q) ||
        m.provider_model_name.toLowerCase().includes(q) ||
        m.provider_kind.toLowerCase().includes(q) ||
        (m.alias ?? '').toLowerCase().includes(q)
      );
    };
    const filtered = all.filter(matches);

    const favorites = filtered.filter((m) => m.is_favorite);
    const favoriteIds = new Set(favorites.map((m) => m.user_model_id));
    const byId = new Map(filtered.map((m) => [m.user_model_id, m]));
    const recentModels = recents
      .map((id) => byId.get(id))
      .filter((m): m is UserModel => Boolean(m) && !favoriteIds.has((m as UserModel).user_model_id));
    const recentIds = new Set(recentModels.map((m) => m.user_model_id));

    const grouped = new Map<string, UserModel[]>();
    for (const m of filtered) {
      if (favoriteIds.has(m.user_model_id) || recentIds.has(m.user_model_id)) continue;
      const group = grouped.get(m.provider_kind) ?? [];
      group.push(m);
      grouped.set(m.provider_kind, group);
    }

    const selected = value ? (models ?? []).find((m) => m.user_model_id === value) : undefined;
    const isOrphan = Boolean(value && models !== null && !selected);

    const sections: Array<{ label: string | null; options: Option[] }> = [];
    if (allowNone) sections.push({ label: null, options: [{ id: '' }] });
    if (isOrphan && value) sections.push({ label: null, options: [{ id: value, orphan: true }] });

    // review-impl MED: when the user has set an EXPLICIT order (any non-null
    // sort_order), honor it as a FLAT list — the server already ordered by
    // sort_order → is_favorite → created_at, so the favorites-hoist + provider
    // grouping below would OVERRIDE the order the card promises. Only fall back
    // to the favorites/recents/by-provider presentation when nothing is ordered.
    const hasCustomOrder = filtered.some((m) => m.sort_order != null);
    if (hasCustomOrder) {
      sections.push({ label: null, options: filtered.map((m) => ({ id: m.user_model_id, model: m })) });
    } else {
      if (favorites.length > 0)
        sections.push({
          label: t('modelPicker.favorites', { defaultValue: 'Favorites' }),
          options: favorites.map((m) => ({ id: m.user_model_id, model: m })),
        });
      if (recentModels.length > 0)
        sections.push({
          label: t('modelPicker.recents', { defaultValue: 'Recent' }),
          options: recentModels.map((m) => ({ id: m.user_model_id, model: m })),
        });
      for (const [kind, group] of grouped) {
        sections.push({ label: kind, options: group.map((m) => ({ id: m.user_model_id, model: m })) });
      }
    }
    const flatOptions = sections.flatMap((s) => s.options);
    return { sections, flatOptions, selectedModel: selected, orphan: isOrphan };
  }, [models, query, recents, value, allowNone, t]);

  // Keep the active row valid as the filter changes.
  useEffect(() => {
    if (activeIndex >= flatOptions.length) setActiveIndex(Math.max(0, flatOptions.length - 1));
  }, [flatOptions.length, activeIndex]);

  const optionDomId = (index: number) => `${listboxId}-opt-${index}`;

  function select(option: Option) {
    if (option.id && !option.orphan) {
      setRecents(pushRecent(capability, option.id, accessToken, userId));
    }
    onChange(option.id === '' ? null : option.id);
    setOpen(false);
    triggerRef.current?.focus();
  }

  function toggleFavorite(model: UserModel) {
    if (!accessToken) return;
    const next = !model.is_favorite;
    // Optimistic flip; revert on failure. Invalidate the shared fetch cache so
    // sibling pickers re-read the new favorites-first server order.
    mutate((ms) => ms.map((m) => (m.user_model_id === model.user_model_id ? { ...m, is_favorite: next } : m)));
    invalidateUserModelsCache();
    aiModelsApi.patchFavorite(accessToken, model.user_model_id, next).catch(() => {
      mutate((ms) =>
        ms.map((m) => (m.user_model_id === model.user_model_id ? { ...m, is_favorite: !next } : m)),
      );
    });
  }

  function onSearchKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, flatOptions.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Home') {
      e.preventDefault();
      setActiveIndex(0);
    } else if (e.key === 'End') {
      e.preventDefault();
      setActiveIndex(Math.max(0, flatOptions.length - 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const option = flatOptions[activeIndex];
      if (option) select(option);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      setOpen(false);
      triggerRef.current?.focus();
    }
  }

  function onTriggerKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      setOpen(true);
    }
  }

  // ── Trigger label ──────────────────────────────────────────────────────────
  const noneText = noneLabel ?? t('modelPicker.none', { defaultValue: 'None' });
  const placeholderText = placeholder ?? t('modelPicker.placeholder', { defaultValue: 'Select a model…' });
  const triggerLabel = selectedModel
    ? getUserModelMeta(selectedModel).displayName
    : orphan
      ? t('modelPicker.orphan', { defaultValue: 'Previously selected model (no longer in your registry)' })
      : value === null && allowNone
        ? noneText
        : placeholderText;

  const isEmpty = models !== null && models.length === 0 && !error;

  if (loading) {
    return (
      <div className={cn(compact ? 'h-7' : 'h-9', 'animate-pulse rounded-md bg-muted', className)} data-testid="model-picker-loading" />
    );
  }

  return (
    <div ref={rootRef} className={cn('relative', className)}>
      <button
        ref={triggerRef}
        type="button"
        role="combobox"
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={open ? listboxId : undefined}
        aria-label={ariaLabel ?? placeholderText}
        disabled={disabled || (isEmpty && !allowNone)}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={onTriggerKeyDown}
        className={cn(
          'flex w-full items-center justify-between gap-2 rounded-md border border-border bg-background text-left text-foreground outline-none transition-colors focus:border-ring disabled:opacity-60',
          compact ? 'h-7 px-2 text-xs' : 'h-9 px-2.5 text-sm',
        )}
      >
        <span className={cn('truncate', !selectedModel && !(value === null && allowNone) && 'text-muted-foreground')}>
          {triggerLabel}
        </span>
        <ChevronsUpDown className={cn('shrink-0 text-muted-foreground', compact ? 'h-3 w-3' : 'h-3.5 w-3.5')} />
      </button>

      {open && (
        <div className="absolute left-0 right-0 z-50 mt-1 overflow-hidden rounded-md border border-border bg-card shadow-lg">
          <div className="relative border-b border-border">
            <Search className="absolute left-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
            <input
              ref={searchRef}
              type="text"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setActiveIndex(0);
              }}
              onKeyDown={onSearchKeyDown}
              placeholder={t('modelPicker.search', { defaultValue: 'Search models…' })}
              aria-label={t('modelPicker.search', { defaultValue: 'Search models…' })}
              aria-controls={listboxId}
              aria-activedescendant={flatOptions.length > 0 ? optionDomId(activeIndex) : undefined}
              className="w-full bg-transparent py-2 pl-7 pr-2 text-xs text-foreground placeholder:text-muted-foreground outline-none"
            />
          </div>
          <ul role="listbox" id={listboxId} className="max-h-64 overflow-y-auto p-1">
            {flatOptions.length === 0 && (
              <li className="px-2 py-3 text-center text-xs text-muted-foreground" role="presentation">
                {t('modelPicker.noResults', { defaultValue: 'No models match your search.' })}
              </li>
            )}
            {(() => {
              let index = -1;
              return sections.map((section, si) => (
                <li key={si} role="presentation">
                  {section.label && (
                    <div className="px-2 pb-0.5 pt-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                      {section.label}
                    </div>
                  )}
                  <ul role="presentation">
                    {section.options.map((option) => {
                      index += 1;
                      return (
                        <OptionRow
                          key={option.id || '__none__'}
                          option={option}
                          domId={optionDomId(index)}
                          active={index === activeIndex}
                          selected={(option.id || null) === value}
                          index={index}
                          noneText={noneText}
                          orphanText={t('modelPicker.orphan', {
                            defaultValue: 'Previously selected model (no longer in your registry)',
                          })}
                          onHover={setActiveIndex}
                          onSelect={select}
                          onToggleFavorite={toggleFavorite}
                          t={t}
                        />
                      );
                    })}
                  </ul>
                </li>
              ));
            })()}
          </ul>
        </div>
      )}

      {error && (
        <p className="mt-1 text-[11px] text-destructive">
          {t('modelPicker.error', { defaultValue: 'Failed to load models.' })}
        </p>
      )}
      {isEmpty &&
        (emptyState ?? (
          <div className="mt-1 flex flex-col gap-1 text-[11px] text-muted-foreground">
            <span>
              {t('modelPicker.empty', { defaultValue: 'No models available. Register one to get started.' })}
            </span>
            <AddModelCta capability={capability} variant="link" />
          </div>
        ))}
    </div>
  );
}

// ── Option row ────────────────────────────────────────────────────────────────

interface OptionRowProps {
  option: Option;
  domId: string;
  active: boolean;
  selected: boolean;
  index: number;
  noneText: string;
  orphanText: string;
  onHover: (index: number) => void;
  onSelect: (option: Option) => void;
  onToggleFavorite: (model: UserModel) => void;
  t: (key: string, opts?: Record<string, unknown>) => string;
}

function OptionRow({
  option,
  domId,
  active,
  selected,
  index,
  noneText,
  orphanText,
  onHover,
  onSelect,
  onToggleFavorite,
  t,
}: OptionRowProps) {
  const model = option.model;
  const meta = model ? getUserModelMeta(model) : null;
  const label = option.orphan ? orphanText : model ? meta!.displayName : noneText;

  return (
    <li
      id={domId}
      role="option"
      aria-selected={selected}
      data-active={active || undefined}
      data-model-id={model?.user_model_id ?? ''}
      onMouseEnter={() => onHover(index)}
      onMouseDown={(e) => e.preventDefault() /* keep search focus */}
      onClick={() => onSelect(option)}
      className={cn(
        'flex cursor-pointer items-center gap-1.5 rounded px-2 py-1.5 text-xs text-foreground',
        active && 'bg-secondary',
        selected && 'font-medium',
      )}
    >
      <span className={cn('min-w-0 flex-1 truncate', option.orphan && 'italic text-muted-foreground')}>
        {label}
      </span>

      {model && meta && (
        <span className="flex shrink-0 items-center gap-1">
          {/* capability icons */}
          {meta.capabilities.map((capToken) => {
            const Icon = CAPABILITY_ICONS[capToken];
            return Icon ? (
              <Icon key={capToken} aria-label={capToken} className="h-3 w-3 text-muted-foreground" />
            ) : null;
          })}
          {/* context length */}
          {model.context_length ? (
            <span className="rounded-full bg-accent/10 px-1.5 py-0.5 text-[10px] text-accent">
              {t('modelPicker.ctx', {
                defaultValue: '{{n}}K',
                n: Math.round(model.context_length / 1024),
              })}
            </span>
          ) : null}
          {/* price hint */}
          {meta.isFree ? (
            <span
              className="rounded-full bg-emerald-500/10 px-1.5 py-0.5 text-[10px] text-emerald-600 dark:text-emerald-400"
              title={t('modelPicker.freeHint', { defaultValue: 'Runs locally — no per-token cost.' })}
            >
              {t('modelPicker.free', { defaultValue: '$0 local' })}
            </span>
          ) : meta.isPriced ? (
            <span
              className="rounded-full bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground"
              title={t('modelPicker.paidHint', { defaultValue: 'Priced per use.' })}
            >
              $
            </span>
          ) : null}
          {/* favorite star */}
          <button
            type="button"
            tabIndex={-1}
            aria-label={
              model.is_favorite
                ? t('modelPicker.unfavorite', { defaultValue: 'Remove from favorites' })
                : t('modelPicker.favorite', { defaultValue: 'Add to favorites' })
            }
            aria-pressed={model.is_favorite}
            onClick={(e) => {
              e.stopPropagation();
              onToggleFavorite(model);
            }}
            className="rounded p-0.5 hover:bg-secondary"
          >
            <Star
              className={cn(
                'h-3 w-3',
                model.is_favorite ? 'fill-primary text-primary' : 'text-muted-foreground',
              )}
            />
          </button>
        </span>
      )}
    </li>
  );
}
