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
const createEventMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      updateEvent: (...a: unknown[]) => updateEventMock(...a),
      createEvent: (...a: unknown[]) => createEventMock(...a),
    },
  };
});

import { EventEditDialog } from '../EventEditDialog';

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
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

// D-KG-EVENT-CREATE-ROUTE — the same dialog authors a NEW event in create mode.
// Kept a top-level sibling (not nested under EventEditDialog): the parent's
// `mockReset()` beforeEach interacts with react-query's mutation teardown to
// mis-flag this negative path's (caught) rejection as unhandled — a vitest quirk,
// not a product bug. A local `mockClear` reset sidesteps it.
describe('EventEditDialog — create mode', () => {
  beforeEach(() => {
    createEventMock.mockClear();
    toastMocks.success.mockClear();
    toastMocks.error.mockClear();
  });

    it('opens blank (no event to seed)', () => {
      render(
        <EventEditDialog open onOpenChange={vi.fn()} create={{ projectId: 'p1', chapterId: 'ch-9', participants: ['Kai'] }} />,
        { wrapper: Wrapper },
      );
      expect((screen.getByTestId('event-edit-title') as HTMLInputElement).value).toBe('');
      expect((screen.getByTestId('event-edit-dateiso') as HTMLInputElement).value).toBe('');
    });

    it('POSTs a create payload with the project + chapter + participant anchor', async () => {
      createEventMock.mockResolvedValue({ ...EVENT, id: 'evt-new', title: 'The Duel' });
      const onOpenChange = vi.fn();
      render(
        <EventEditDialog open onOpenChange={onOpenChange} create={{ projectId: 'p1', chapterId: 'ch-9', participants: ['Kai'] }} />,
        { wrapper: Wrapper },
      );
      fireEvent.change(screen.getByTestId('event-edit-title'), { target: { value: 'The Duel' } });
      fireEvent.click(screen.getByTestId('event-edit-confirm'));
      await waitFor(() => {
        expect(createEventMock).toHaveBeenCalledWith(
          { project_id: 'p1', title: 'The Duel', chapter_id: 'ch-9', participants: ['Kai'] },
          'tok',
        );
      });
      await waitFor(() => expect(toastMocks.success).toHaveBeenCalledTimes(1));
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });

    it('a blank title cannot submit (button disabled — no silent no-op)', () => {
      render(
        <EventEditDialog open onOpenChange={vi.fn()} create={{ projectId: 'p1' }} />,
        { wrapper: Wrapper },
      );
      expect((screen.getByTestId('event-edit-confirm') as HTMLButtonElement).disabled).toBe(true);
      fireEvent.click(screen.getByTestId('event-edit-confirm'));
      expect(createEventMock).not.toHaveBeenCalled();
    });

    it('surfaces a create failure as an error toast', async () => {
      // Per-call rejection (not mockRejectedValue, whose eagerly-created rejected
      // promise can read as unobserved under the reset/teardown timing here).
      createEventMock.mockImplementation(() => Promise.reject(new Error('boom')));
      render(
        <EventEditDialog open onOpenChange={vi.fn()} create={{ projectId: 'p1', participants: ['Kai'] }} />,
        { wrapper: Wrapper },
      );
      fireEvent.change(screen.getByTestId('event-edit-title'), { target: { value: 'The Duel' } });
      fireEvent.click(screen.getByTestId('event-edit-confirm'));
      await waitFor(() => expect(toastMocks.error).toHaveBeenCalled());
    });
});
