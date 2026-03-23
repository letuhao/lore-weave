import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useEntityKinds } from '@/features/glossary/hooks/useEntityKinds';
import { CreateEntityModal } from '@/features/glossary/components/CreateEntityModal';
import { KindBadge } from '@/features/glossary/components/KindBadge';
import type { EntityKind } from '@/features/glossary/types';

/**
 * SP-1 skeleton: loads entity kinds, renders kind picker modal trigger.
 * Entity list and detail panel are added in SP-2.
 */
export function GlossaryPage() {
  const { bookId = '' } = useParams();
  const { kinds, isLoading, error } = useEntityKinds();
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  function handleKindSelect(_kind: EntityKind) {
    // Entity creation wired in SP-2; close modal for now.
    setIsCreateOpen(false);
  }

  if (isLoading) {
    return (
      <div className="space-y-4 p-6">
        <div className="h-6 w-32 animate-pulse rounded bg-muted" />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="h-16 animate-pulse rounded border bg-muted" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <p className="text-sm text-destructive">{error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Glossary</h1>
          <p className="text-xs text-muted-foreground">
            Book ID: {bookId} · {kinds.length} entity types available
          </p>
        </div>
        <button
          onClick={() => setIsCreateOpen(true)}
          className="rounded border px-3 py-1.5 text-sm font-medium hover:bg-muted"
        >
          + New Entity
        </button>
      </div>

      {/* Kind catalogue preview */}
      <div>
        <p className="mb-3 text-sm font-medium text-muted-foreground">Available entity types</p>
        <div className="flex flex-wrap gap-2">
          {kinds.map((k) => (
            <KindBadge key={k.kind_id} kind={k} size="md" />
          ))}
        </div>
      </div>

      {/* Entity list — placeholder until SP-2 */}
      <div className="rounded border p-8 text-center text-sm text-muted-foreground">
        No entities yet. Click <strong>+ New Entity</strong> to create your first.
      </div>

      {isCreateOpen && (
        <CreateEntityModal
          kinds={kinds}
          onSelect={handleKindSelect}
          onClose={() => setIsCreateOpen(false)}
        />
      )}
    </div>
  );
}
