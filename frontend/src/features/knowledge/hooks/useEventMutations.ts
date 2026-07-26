import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import {
  knowledgeApi,
  type EventCreatePayload,
  type EventUpdatePayload,
  type TimelineEvent,
} from '../api';

// Phase B C-FE — event correction mutation hooks.
//
// Events render in the timeline list, so both invalidate the
// ['knowledge-timeline', userId] prefix (covers every project/order filter the
// user may have open). update carries If-Match (BE 428s without it); on a 412
// conflict we re-invalidate the timeline so the row's version baseline
// refreshes before a retry.

export interface UseUpdateEventResult {
  update: (args: {
    eventId: string;
    payload: EventUpdatePayload;
    /** C2: version from the event the user is editing. Sent as If-Match. */
    ifMatchVersion: number;
  }) => Promise<TimelineEvent>;
  isPending: boolean;
  error: Error | null;
}

export function useUpdateEvent(options?: {
  onSuccess?: (event: TimelineEvent) => void;
  onError?: (err: Error) => void;
}): UseUpdateEventResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async (args: {
      eventId: string;
      payload: EventUpdatePayload;
      ifMatchVersion: number;
    }) =>
      knowledgeApi.updateEvent(
        args.eventId,
        args.payload,
        args.ifMatchVersion,
        accessToken!,
      ),
    onSuccess: async (event) => {
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-timeline', userId],
      });
      options?.onSuccess?.(event);
    },
    onError: async (err) => {
      const status = (err as Error & { status?: number }).status;
      if (status === 412) {
        await queryClient.invalidateQueries({
          queryKey: ['knowledge-timeline', userId],
        });
      }
      options?.onError?.(err as Error);
    },
  });

  return {
    update: mutation.mutateAsync,
    isPending: mutation.isPending,
    error: (mutation.error as Error | null) ?? null,
  };
}

export interface UseCreateEventResult {
  create: (payload: EventCreatePayload) => Promise<TimelineEvent>;
  isPending: boolean;
  error: Error | null;
}

/**
 * D-KG-EVENT-CREATE-ROUTE — author a new timeline event.
 *
 * Invalidates the ['knowledge-timeline', userId] prefix (the Timeline tab) AND
 * the ['composition', 'arc'] / ['composition', 'cast'] prefixes: the Character-Arc
 * view (the primary "+ Add event" launcher) reads its events under the composition
 * namespace, so a knowledge-only invalidation would leave the freshly-authored
 * event invisible on the arc until a manual refetch.
 */
export function useCreateEvent(options?: {
  onSuccess?: (event: TimelineEvent) => void;
  onError?: (err: Error) => void;
}): UseCreateEventResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async (payload: EventCreatePayload) =>
      knowledgeApi.createEvent(payload, accessToken!),
    onSuccess: async (event) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['knowledge-timeline', userId] }),
        queryClient.invalidateQueries({ queryKey: ['composition', 'arc'] }),
        queryClient.invalidateQueries({ queryKey: ['composition', 'cast'] }),
      ]);
      options?.onSuccess?.(event);
    },
    onError: (err) => options?.onError?.(err as Error),
  });

  return {
    create: mutation.mutateAsync,
    isPending: mutation.isPending,
    error: (mutation.error as Error | null) ?? null,
  };
}

export interface UseArchiveEventResult {
  archive: (args: { eventId: string }) => Promise<void>;
  isPending: boolean;
  error: Error | null;
}

/** Soft-archive an event (user "delete"). */
export function useArchiveEvent(options?: {
  onSuccess?: () => void;
  onError?: (err: Error) => void;
}): UseArchiveEventResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async (args: { eventId: string }) =>
      knowledgeApi.archiveEvent(args.eventId, accessToken!),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-timeline', userId],
      });
      options?.onSuccess?.();
    },
    onError: (err) => options?.onError?.(err as Error),
  });

  return {
    archive: mutation.mutateAsync,
    isPending: mutation.isPending,
    error: (mutation.error as Error | null) ?? null,
  };
}
