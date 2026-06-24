// LOOM Composition (T3.5) — Style & Voice controllers.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { compositionApi } from '../api';
import type { StyleProfile, StyleScope, VoiceProfile } from '../types';

const styleKey = (projectId?: string) => ['composition', 'style-profiles', projectId];
const voiceKey = (projectId?: string) => ['composition', 'voice-profiles', projectId];

export function useStyleProfiles(projectId: string | undefined, token: string | null) {
  return useQuery({
    queryKey: styleKey(projectId),
    queryFn: () => compositionApi.getStyleProfiles(projectId!, token!),
    enabled: !!projectId && !!token,
    select: (d): StyleProfile[] => d.items,
  });
}

export function useSetStyleProfile(projectId: string | undefined, token: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: StyleProfile) => compositionApi.putStyleProfile(projectId!, body, token!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: styleKey(projectId) });
      // the resolved style surfaces in the grounding preview profile
      qc.invalidateQueries({ queryKey: ['composition', 'grounding', projectId] });
    },
  });
}

export function useDeleteStyleProfile(projectId: string | undefined, token: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { scopeType: StyleScope; scopeId: string }) =>
      compositionApi.deleteStyleProfile(projectId!, v.scopeType, v.scopeId, token!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: styleKey(projectId) });
      qc.invalidateQueries({ queryKey: ['composition', 'grounding', projectId] });
    },
  });
}

export function useVoiceProfiles(projectId: string | undefined, token: string | null) {
  return useQuery({
    queryKey: voiceKey(projectId),
    queryFn: () => compositionApi.getVoiceProfiles(projectId!, token!),
    enabled: !!projectId && !!token,
    select: (d): VoiceProfile[] => d.items,
  });
}

export function useSetVoiceProfile(projectId: string | undefined, token: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: VoiceProfile) => compositionApi.putVoiceProfile(projectId!, body, token!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: voiceKey(projectId) });
      qc.invalidateQueries({ queryKey: ['composition', 'grounding', projectId] });
    },
  });
}

export function useDeleteVoiceProfile(projectId: string | undefined, token: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (entityId: string) => compositionApi.deleteVoiceProfile(projectId!, entityId, token!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: voiceKey(projectId) });
      qc.invalidateQueries({ queryKey: ['composition', 'grounding', projectId] });
    },
  });
}
