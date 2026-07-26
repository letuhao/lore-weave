import { render, screen, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { DragEndEvent } from '@dnd-kit/core';

// (8)-residual — the drag-reorder list that persists a user-defined model order.
// Real pointer/keyboard dnd doesn't work in jsdom, so we mock @dnd-kit/core's
// DndContext to CAPTURE its onDragEnd handler and invoke it deterministically —
// proving the reorder → API-persist wiring. arrayMove stays real (partial mock).

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

let capturedOnDragEnd: ((e: DragEndEvent) => void) | null = null;
vi.mock('@dnd-kit/core', () => ({
  DndContext: ({ children, onDragEnd }: { children: React.ReactNode; onDragEnd: (e: DragEndEvent) => void }) => {
    capturedOnDragEnd = onDragEnd;
    return children;
  },
  closestCenter: vi.fn(),
  PointerSensor: vi.fn(),
  KeyboardSensor: vi.fn(),
  useSensor: vi.fn(),
  useSensors: vi.fn(() => []),
}));

vi.mock('@dnd-kit/sortable', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@dnd-kit/sortable')>();
  return {
    ...actual, // keep the real arrayMove
    SortableContext: ({ children }: { children: React.ReactNode }) => children,
    sortableKeyboardCoordinates: vi.fn(),
    verticalListSortingStrategy: vi.fn(),
    useSortable: () => ({
      attributes: {},
      listeners: {},
      setNodeRef: () => {},
      transform: null,
      transition: undefined,
      isDragging: false,
    }),
  };
});

const reorderUserModels = vi.fn();
vi.mock('@/features/ai-models/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/ai-models/api')>();
  return {
    ...actual, // keep getUserModelMeta
    aiModelsApi: {
      reorderUserModels: (...a: unknown[]) => reorderUserModels(...a),
    },
  };
});

const listUserModels = vi.fn();
const invalidateUserModelsCache = vi.fn();
vi.mock('@/components/model-picker/useUserModels', () => ({
  invalidateUserModelsCache: (...a: unknown[]) => invalidateUserModelsCache(...a),
}));
vi.mock('../api', () => ({
  providerApi: { listUserModels: (...a: unknown[]) => listUserModels(...a) },
}));

import { ModelOrderCard } from '../ModelOrderCard';

function m(id: string, extra: Record<string, unknown> = {}) {
  return {
    user_model_id: id,
    provider_credential_id: 'c1',
    provider_kind: 'lm_studio',
    provider_model_name: id,
    is_active: true,
    is_favorite: false,
    tags: [],
    created_at: '2026-01-01T00:00:00Z',
    ...extra,
  };
}

beforeEach(() => {
  capturedOnDragEnd = null;
  reorderUserModels.mockReset();
  listUserModels.mockReset();
  invalidateUserModelsCache.mockReset();
  reorderUserModels.mockResolvedValue({ items: [] });
});

describe('ModelOrderCard', () => {
  it('renders all models in the server-provided order', async () => {
    listUserModels.mockResolvedValue({ items: [m('a'), m('b'), m('c')] });
    render(<ModelOrderCard />);

    await waitFor(() => expect(screen.getAllByTestId('model-order-row')).toHaveLength(3));
    const ids = screen.getAllByTestId('model-order-row').map((el) => el.getAttribute('data-model-id'));
    expect(ids).toEqual(['a', 'b', 'c']);
  });

  it('persists the reordered id list via reorderUserModels + invalidates the picker cache', async () => {
    listUserModels.mockResolvedValue({ items: [m('a'), m('b'), m('c')] });
    // Server echoes the new canonical order back.
    reorderUserModels.mockResolvedValue({ items: [m('c'), m('a'), m('b')] });
    render(<ModelOrderCard />);
    await waitFor(() => expect(screen.getAllByTestId('model-order-row')).toHaveLength(3));

    // Drag 'c' onto 'a' → new order [c, a, b].
    expect(capturedOnDragEnd).not.toBeNull();
    capturedOnDragEnd!({ active: { id: 'c' }, over: { id: 'a' } } as unknown as DragEndEvent);

    await waitFor(() => expect(reorderUserModels).toHaveBeenCalledTimes(1));
    expect(reorderUserModels).toHaveBeenCalledWith('tok', ['c', 'a', 'b']);
    expect(invalidateUserModelsCache).toHaveBeenCalled();

    // Adopts server truth in the rendered order.
    await waitFor(() => {
      const ids = screen.getAllByTestId('model-order-row').map((el) => el.getAttribute('data-model-id'));
      expect(ids).toEqual(['c', 'a', 'b']);
    });
  });

  it('is a no-op when dropped on itself (no API call)', async () => {
    listUserModels.mockResolvedValue({ items: [m('a'), m('b')] });
    render(<ModelOrderCard />);
    await waitFor(() => expect(screen.getAllByTestId('model-order-row')).toHaveLength(2));

    capturedOnDragEnd!({ active: { id: 'a' }, over: { id: 'a' } } as unknown as DragEndEvent);
    expect(reorderUserModels).not.toHaveBeenCalled();
  });

  it('hides the card when fewer than two models exist', async () => {
    listUserModels.mockResolvedValue({ items: [m('only')] });
    const { container } = render(<ModelOrderCard />);
    await waitFor(() => expect(screen.queryByTestId('model-order-loading')).toBeNull());
    expect(within(container).queryByTestId('model-order-card')).toBeNull();
  });
});
