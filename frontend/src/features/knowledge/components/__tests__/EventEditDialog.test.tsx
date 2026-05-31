import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({
  useAuth: () => ({
    accessToken: 'tok',
    user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
  }),
}));

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock('sonner', () => ({ toast: toastMocks }));

const updateEventMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: { updateEvent: (...a: unknown[]) => updateEventMock(...a) },
  };
});

import { EventEditDialog } from '../EventEditDialog';

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const EVENT = {
  id: 'evt-1', user_id: 'u1', project_id: null,
  title: 'The Oath', canonical_title: 'the oath', summary: 'They swore.',
  chapter_id: 'ch-1', chapter_title: null, event_order: 1, chronological_order: null,
  event_date_iso: '0184', time_cue: 'dawn', participants: ['Liu'], confidence: 0.9,
  source_types: ['book_content'], evidence_count: 1, mention_count: 1,
  archived_at: null, version: 5, created_at: null, updated_at: null,
};

describe('EventEditDialog', () => {
  beforeEach(() => {
    updateEventMock.mockReset();
    toastMocks.success.mockReset();
    toastMocks.error.mockReset();
  });

  it('pre-fills fields from the event', () => {
    render(<EventEditDialog open onOpenChange={vi.fn()} event={EVENT} />, { wrapper: Wrapper });
    expect((screen.getByTestId('event-edit-title') as HTMLInputElement).value).toBe('The Oath');
    expect((screen.getByTestId('event-edit-dateiso') as HTMLInputElement).value).toBe('0184');
  });

  it('submits only changed fields with If-Match version', async () => {
    updateEventMock.mockResolvedValue({ ...EVENT, title: 'The Peach Garden Oath' });
    const onOpenChange = vi.fn();
    render(<EventEditDialog open onOpenChange={onOpenChange} event={EVENT} />, { wrapper: Wrapper });
    fireEvent.change(screen.getByTestId('event-edit-title'), {
      target: { value: 'The Peach Garden Oath' },
    });
    fireEvent.click(screen.getByTestId('event-edit-confirm'));
    await waitFor(() => {
      expect(updateEventMock).toHaveBeenCalledWith(
        'evt-1',
        { title: 'The Peach Garden Oath', summary: undefined, time_cue: undefined, event_date_iso: undefined },
        5,
        'tok',
      );
    });
    await waitFor(() => expect(toastMocks.success).toHaveBeenCalledTimes(1));
  });

  it('closes without calling API when nothing changed', async () => {
    const onOpenChange = vi.fn();
    render(<EventEditDialog open onOpenChange={onOpenChange} event={EVENT} />, { wrapper: Wrapper });
    fireEvent.click(screen.getByTestId('event-edit-confirm'));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(updateEventMock).not.toHaveBeenCalled();
  });

  it('shows conflict toast and closes on 412', async () => {
    updateEventMock.mockRejectedValue(Object.assign(new Error('mismatch'), { status: 412 }));
    const onOpenChange = vi.fn();
    render(<EventEditDialog open onOpenChange={onOpenChange} event={EVENT} />, { wrapper: Wrapper });
    fireEvent.change(screen.getByTestId('event-edit-title'), { target: { value: 'X' } });
    fireEvent.click(screen.getByTestId('event-edit-confirm'));
    await waitFor(() => expect(toastMocks.error).toHaveBeenCalledWith('events.edit.conflict'));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
