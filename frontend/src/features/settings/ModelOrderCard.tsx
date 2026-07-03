import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { GripVertical, Star } from 'lucide-react';
import {
  DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { aiModelsApi, getUserModelMeta, type UserModel } from '@/features/ai-models/api';
import { invalidateUserModelsCache } from '@/components/model-picker/useUserModels';
import { providerApi } from './api';

/**
 * (8)-residual — user-defined custom SORT ORDER for models. A drag-reorder list
 * over ALL the user's registered models that persists to provider-registry (PUT
 * /user-models/reorder). The shared ModelPicker renders models in the server's
 * `sort_order ASC NULLS LAST, is_favorite DESC` order, so a reorder here changes
 * the picker order everywhere (favorites still pin on top when a model has no
 * explicit position). Server is the SSOT — nothing is stored in localStorage, so
 * the order follows the user across devices.
 */
export function ModelOrderCard() {
  const { t } = useTranslation('common');
  const { accessToken } = useAuth();
  const [items, setItems] = useState<UserModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  // Guards a stale reload from clobbering an in-flight optimistic reorder.
  const savingRef = useRef(false);

  const load = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      // include_inactive=true (providerApi default) — the management list shows
      // deactivated models too, and they carry a position as well.
      const res = await providerApi.listUserModels(accessToken);
      if (!savingRef.current) setItems(res.items ?? []);
    } catch {
      toast.error(t('modelOrder.loadFailed', { defaultValue: 'Failed to load models.' }));
    } finally {
      setLoading(false);
    }
    // `t` is stable in production (react-i18next) — intentionally excluded so this
    // effect-feeding callback isn't recreated every render (which would refetch).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken]);

  useEffect(() => {
    void load();
  }, [load]);

  const sensors = useSensors(
    // 5px activation keeps a plain click from starting a drag; keyboard sensor
    // makes reorder a11y-operable.
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const persist = useCallback(
    async (ordered: UserModel[]) => {
      if (!accessToken) return;
      const prev = items;
      setItems(ordered); // optimistic
      setSaving(true);
      savingRef.current = true;
      // The shared picker cache must be dropped so every sibling picker re-reads
      // the new server order on its next mount.
      invalidateUserModelsCache();
      try {
        const res = await aiModelsApi.reorderUserModels(
          accessToken,
          ordered.map((m) => m.user_model_id),
        );
        // Adopt server truth (canonical sort_order stamped).
        if (res.items) setItems(res.items);
        toast.success(t('modelOrder.saved', { defaultValue: 'Model order saved' }));
      } catch (e) {
        setItems(prev); // rollback
        toast.error((e as Error).message || t('modelOrder.saveFailed', { defaultValue: 'Failed to save order.' }));
      } finally {
        setSaving(false);
        savingRef.current = false;
      }
    },
    // `t` stable in production; not an effect dep. See load() above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [accessToken, items],
  );

  function handleDragEnd(e: DragEndEvent) {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    const from = items.findIndex((m) => m.user_model_id === active.id);
    const to = items.findIndex((m) => m.user_model_id === over.id);
    if (from < 0 || to < 0) return;
    void persist(arrayMove(items, from, to));
  }

  if (loading) {
    return <div className="mb-4 h-32 animate-pulse rounded-lg border bg-card" data-testid="model-order-loading" />;
  }

  // Nothing to order until at least two models exist.
  if (items.length < 2) return null;

  return (
    <div className="mb-4 rounded-lg border bg-card p-4" data-testid="model-order-card">
      <div className="mb-3">
        <h3 className="text-sm font-semibold">{t('modelOrder.heading', { defaultValue: 'Model order' })}</h3>
        <p className="text-xs text-muted-foreground">
          {t('modelOrder.subtitle', {
            defaultValue: 'Drag to set the order models appear in every picker. Saved to your account (syncs across devices). Favorites still show first when a model has no set position.',
          })}
        </p>
      </div>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={items.map((m) => m.user_model_id)} strategy={verticalListSortingStrategy}>
          <ul className={cn('overflow-hidden rounded-md border', saving && 'opacity-70')}>
            {items.map((m) => (
              <ModelOrderRow key={m.user_model_id} model={m} dragLabel={t('modelOrder.dragAria', { defaultValue: 'Reorder model' })} />
            ))}
          </ul>
        </SortableContext>
      </DndContext>
    </div>
  );
}

function ModelOrderRow({ model, dragLabel }: { model: UserModel; dragLabel: string }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: model.user_model_id,
  });
  const meta = getUserModelMeta(model);
  return (
    <li
      ref={setNodeRef}
      data-testid="model-order-row"
      data-model-id={model.user_model_id}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        ...(isDragging ? { zIndex: 1, position: 'relative' as const } : {}),
      }}
      className={cn(
        'flex items-center gap-2 border-t bg-card px-3 py-2 first:border-t-0',
        !model.is_active && 'opacity-50',
        isDragging && 'opacity-70',
      )}
    >
      <button
        type="button"
        aria-label={dragLabel}
        className="cursor-grab touch-none rounded p-0.5 text-muted-foreground hover:bg-secondary active:cursor-grabbing"
        {...attributes}
        {...listeners}
      >
        <GripVertical className="h-3.5 w-3.5" />
      </button>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="truncate text-[13px] font-medium">{meta.displayName}</span>
          {model.is_favorite && <Star className="h-3 w-3 shrink-0 fill-primary text-primary" aria-hidden />}
        </div>
        <span className="block truncate font-mono text-[10px] text-muted-foreground">{model.provider_model_name}</span>
      </div>
      <span className="shrink-0 rounded-full bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
        {model.provider_kind}
      </span>
    </li>
  );
}
