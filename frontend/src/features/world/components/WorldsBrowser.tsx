import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Globe2, Plus, Trash2 } from 'lucide-react';
import { FormDialog, EmptyState } from '@/components/shared';
import { useWorlds } from '../hooks/useWorlds';
import type { World } from '../types';

// C21 — Worlds HOME browser. Lists the caller's worlds + a create-world flow.
// On create, lands the user in the world workspace (no manuscript). View-only
// component: all list/create logic lives in useWorlds (FE MVC).
export function WorldsBrowser() {
  const { t } = useTranslation('world');
  const navigate = useNavigate();
  const { items, isLoading, createWorld, isCreating, deleteWorld, isDeleting } = useWorlds();

  const [open, setOpen] = useState(false);
  // P3 — the world pending deletion. Irreversible, so it is always a two-step.
  const [pendingDelete, setPendingDelete] = useState<World | null>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');

  const submit = async () => {
    if (!name.trim()) return;
    try {
      const world = await createWorld({ name: name.trim(), description: description.trim() || undefined });
      setOpen(false);
      setName('');
      setDescription('');
      // Land directly in the new world's workspace (prose-less; no manuscript).
      navigate(`/worlds/${world.world_id}`);
    } catch (e) {
      toast.error((e as Error).message || t('create.error', { defaultValue: 'Failed to create world' }));
    }
  };

  return (
    <div className="space-y-4" data-testid="worlds-browser">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-serif text-xl font-semibold">{t('page.title', { defaultValue: 'Worlds' })}</h1>
          <p className="text-sm text-muted-foreground">
            {t('page.subtitle', {
              defaultValue: 'Build a world from its lore — characters, places, factions — with no manuscript required.',
            })}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          data-testid="create-world-button"
        >
          <Plus className="h-4 w-4" />
          {t('create.cta', { defaultValue: 'New world' })}
        </button>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">{t('page.loading', { defaultValue: 'Loading worlds…' })}</p>
      ) : items.length === 0 ? (
        <EmptyState
          icon={Globe2}
          title={t('empty.title', { defaultValue: 'No worlds yet' })}
          description={t('empty.description', {
            defaultValue: 'Create your first world to start authoring lore — no chapters needed.',
          })}
        />
      ) : (
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="worlds-list">
          {items.map((w) => (
            <li key={w.world_id} className="relative">
              {/* P3 — the manual path for `world_delete`, which the agent called 92 times and
                  got right ZERO times (always missing world_id), while the UI offered no way to
                  do it by hand at all. Outside the card button: nesting a button inside a button
                  is invalid HTML and the click would navigate instead of deleting. */}
              <button
                type="button"
                onClick={() => setPendingDelete(w)}
                disabled={w.book_count > 0}
                title={w.book_count > 0
                  ? t('card.delete_blocked', {
                      defaultValue: 'Move its {{count}} book(s) out of this world first',
                      count: w.book_count,
                    })
                  : t('card.delete', { defaultValue: 'Delete world' })}
                aria-label={t('card.delete', { defaultValue: 'Delete world' })}
                data-testid={`world-delete-${w.world_id}`}
                className="absolute right-2 top-2 z-10 rounded p-1.5 text-muted-foreground/60 transition-colors hover:bg-destructive/10 hover:text-destructive disabled:cursor-not-allowed disabled:opacity-30"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => navigate(`/worlds/${w.world_id}`)}
                className="flex w-full flex-col items-start gap-1 rounded-lg border bg-card p-4 text-left transition-colors hover:border-primary/50"
                data-testid={`world-card-${w.world_id}`}
              >
                <span className="flex items-center gap-2 font-medium">
                  <Globe2 className="h-4 w-4 text-muted-foreground" />
                  {w.name}
                </span>
                {w.description && (
                  <span className="line-clamp-2 text-xs text-muted-foreground">{w.description}</span>
                )}
                <span className="mt-1 text-[11px] text-muted-foreground/70">
                  {t('card.books', { defaultValue: '{{count}} books', count: w.book_count })}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* P3 — irreversible, so it is confirmed by name rather than a bare OK. The guard is
          enforced in useWorlds' mutation as well: a disabled button is a hint, not a guarantee. */}
      <FormDialog
        open={!!pendingDelete}
        onOpenChange={(o) => !o && setPendingDelete(null)}
        title={t('card.delete_title', { defaultValue: 'Delete this world?' })}
        description={t('card.delete_description', {
          defaultValue:
            'Deleting "{{name}}" cannot be undone. Its lore, maps and timeline go with it.',
          name: pendingDelete?.name ?? '',
        })}
        footer={
          <>
            <button
              type="button"
              onClick={() => setPendingDelete(null)}
              className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary"
            >
              {t('card.delete_cancel', { defaultValue: 'Cancel' })}
            </button>
            <button
              type="button"
              disabled={isDeleting}
              data-testid="world-delete-confirm"
              onClick={async () => {
                if (!pendingDelete) return;
                try {
                  await deleteWorld(pendingDelete);
                  toast.success(t('card.delete_done', { defaultValue: 'World deleted' }));
                  setPendingDelete(null);
                } catch (e) {
                  toast.error(e instanceof Error ? e.message : String(e));
                }
              }}
              className="rounded-md bg-destructive px-3 py-1.5 text-xs font-medium text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50"
            >
              {t('card.delete_confirm', { defaultValue: 'Delete permanently' })}
            </button>
          </>
        }
      >
        <p className="text-xs text-muted-foreground">
          {t('card.delete_hint', {
            defaultValue: 'A world with books cannot be deleted — move them out first.',
          })}
        </p>
      </FormDialog>

      <FormDialog
        open={open}
        onOpenChange={setOpen}
        title={t('create.title', { defaultValue: 'New world' })}
        description={t('create.description', { defaultValue: 'Name your world. You can author its lore right away.' })}
        footer={
          <>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-md border px-3 py-2 text-sm hover:bg-muted"
            >
              {t('create.cancel', { defaultValue: 'Cancel' })}
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={!name.trim() || isCreating}
              className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              data-testid="create-world-submit"
            >
              {isCreating
                ? t('create.creating', { defaultValue: 'Creating…' })
                : t('create.submit', { defaultValue: 'Create world' })}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <label className="block space-y-1">
            <span className="text-sm font-medium">{t('create.nameLabel', { defaultValue: 'World name' })}</span>
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              placeholder={t('create.namePlaceholder', { defaultValue: 'e.g. The Shattered Realms' })}
              data-testid="create-world-name"
            />
          </label>
          <label className="block space-y-1">
            <span className="text-sm font-medium">{t('create.descLabel', { defaultValue: 'Description (optional)' })}</span>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              data-testid="create-world-desc"
            />
          </label>
        </div>
      </FormDialog>
    </div>
  );
}
