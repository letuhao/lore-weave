import { useEffect, useState } from 'react';
import { Settings2, Type, Hash, Calendar, Link2, ToggleLeft, List, AlignLeft, Tag, ChevronRight } from 'lucide-react';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';
import { type EntityKind, type AttributeDefinition, type FieldType } from '@/features/glossary/types';
import { Skeleton } from '@/components/shared/Skeleton';
import { cn } from '@/lib/utils';

const FIELD_ICONS: Record<FieldType, typeof Type> = {
  text: Type,
  textarea: AlignLeft,
  select: List,
  number: Hash,
  date: Calendar,
  tags: Tag,
  url: Link2,
  boolean: ToggleLeft,
};

const FIELD_LABELS: Record<FieldType, string> = {
  text: 'Text',
  textarea: 'Long text',
  select: 'Select',
  number: 'Number',
  date: 'Date',
  tags: 'Tags',
  url: 'URL',
  boolean: 'Boolean',
};

function AttributeRow({ attr }: { attr: AttributeDefinition }) {
  const Icon = FIELD_ICONS[attr.field_type] ?? Type;
  return (
    <div className="flex items-center gap-3 px-4 py-2.5 border-b last:border-b-0 hover:bg-card/50 transition-colors">
      <Icon className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium truncate">{attr.name}</span>
          {attr.is_required && (
            <span className="rounded bg-amber-400/15 px-1 py-0.5 text-[9px] font-medium text-amber-400">required</span>
          )}
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="text-[10px] text-muted-foreground">{FIELD_LABELS[attr.field_type]}</span>
          <span className="text-[10px] text-muted-foreground font-mono">{attr.code}</span>
          {attr.options && attr.options.length > 0 && (
            <span className="text-[10px] text-muted-foreground">· {attr.options.length} options</span>
          )}
        </div>
      </div>
    </div>
  );
}

export function KindEditor({ onClose }: { onClose: () => void }) {
  const { accessToken } = useAuth();
  const [kinds, setKinds] = useState<EntityKind[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    glossaryApi.getKinds(accessToken)
      .then((k) => {
        setKinds(k);
        if (k.length > 0 && !selectedId) setSelectedId(k[0].kind_id);
      })
      .finally(() => setLoading(false));
  }, [accessToken]);

  const selected = kinds.find((k) => k.kind_id === selectedId);
  const systemKinds = kinds.filter((k) => k.is_default);
  const userKinds = kinds.filter((k) => !k.is_default);

  if (loading) {
    return (
      <div className="space-y-3 p-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Settings2 className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Entity Kinds</h3>
          <span className="text-xs text-muted-foreground">{kinds.length} kinds</span>
        </div>
        <button
          onClick={onClose}
          className="rounded-md border px-3 py-1 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
        >
          Back to Glossary
        </button>
      </div>

      {/* Two-panel layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: kind list */}
        <div className="w-64 flex-shrink-0 border-r overflow-y-auto">
          {systemKinds.length > 0 && (
            <div>
              <div className="px-4 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                System Kinds
              </div>
              {systemKinds.map((k) => (
                <button
                  key={k.kind_id}
                  onClick={() => setSelectedId(k.kind_id)}
                  className={cn(
                    'flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-xs transition-colors border-b',
                    selectedId === k.kind_id
                      ? 'bg-primary/5 border-l-2 border-l-primary'
                      : 'hover:bg-card/50',
                  )}
                >
                  <span className="text-base">{k.icon}</span>
                  <div className="flex-1 min-w-0">
                    <span className="font-medium truncate block">{k.name}</span>
                    <span className="text-[10px] text-muted-foreground">
                      {k.default_attributes.length} attribute{k.default_attributes.length !== 1 ? 's' : ''}
                    </span>
                  </div>
                  {selectedId === k.kind_id && <ChevronRight className="h-3 w-3 text-primary" />}
                </button>
              ))}
            </div>
          )}
          {userKinds.length > 0 && (
            <div>
              <div className="px-4 py-2 text-[10px] font-semibold uppercase tracking-wider text-primary">
                User Kinds
              </div>
              {userKinds.map((k) => (
                <button
                  key={k.kind_id}
                  onClick={() => setSelectedId(k.kind_id)}
                  className={cn(
                    'flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-xs transition-colors border-b',
                    selectedId === k.kind_id
                      ? 'bg-primary/5 border-l-2 border-l-primary'
                      : 'hover:bg-card/50',
                  )}
                >
                  <span className="text-base">{k.icon}</span>
                  <div className="flex-1 min-w-0">
                    <span className="font-medium truncate block">{k.name}</span>
                    <span className="text-[10px] text-muted-foreground">
                      {k.default_attributes.length} attribute{k.default_attributes.length !== 1 ? 's' : ''}
                    </span>
                  </div>
                  {selectedId === k.kind_id && <ChevronRight className="h-3 w-3 text-primary" />}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Right: kind detail + attributes */}
        <div className="flex-1 overflow-y-auto">
          {selected ? (
            <div>
              {/* Kind header */}
              <div className="border-b px-6 py-4">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">{selected.icon}</span>
                  <div>
                    <h4 className="text-sm font-semibold">{selected.name}</h4>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="font-mono text-[10px] text-muted-foreground">{selected.code}</span>
                      <span
                        className="inline-block h-2.5 w-2.5 rounded-full"
                        style={{ backgroundColor: selected.color }}
                        title={selected.color}
                      />
                      {selected.is_default && (
                        <span className="rounded bg-secondary px-1.5 py-0.5 text-[9px] text-muted-foreground">system</span>
                      )}
                      {selected.is_hidden && (
                        <span className="rounded bg-secondary px-1.5 py-0.5 text-[9px] text-muted-foreground">hidden</span>
                      )}
                    </div>
                  </div>
                </div>
                {selected.genre_tags.length > 0 && (
                  <div className="mt-3 flex items-center gap-1.5">
                    <span className="text-[10px] text-muted-foreground">Genres:</span>
                    {selected.genre_tags.map((tag) => (
                      <span key={tag} className="rounded-full border px-2 py-0.5 text-[10px] text-muted-foreground">{tag}</span>
                    ))}
                  </div>
                )}
              </div>

              {/* Attributes */}
              <div className="px-6 py-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold">
                    Attributes ({selected.default_attributes.length})
                  </span>
                </div>
                {selected.default_attributes.length === 0 ? (
                  <p className="text-xs text-muted-foreground italic py-4">No attributes defined.</p>
                ) : (
                  <div className="rounded-lg border">
                    {[...selected.default_attributes]
                      .sort((a, b) => a.sort_order - b.sort_order)
                      .map((attr) => (
                        <AttributeRow key={attr.attr_def_id} attr={attr} />
                      ))}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center h-full text-xs text-muted-foreground">
              Select a kind to view its attributes
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
