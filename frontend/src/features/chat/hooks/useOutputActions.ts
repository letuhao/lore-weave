import { useCallback } from 'react';
import { useAuth } from '@/auth';
import { chatApi } from '../api';
import type { ChatOutput } from '../types';

export function useOutputActions() {
  const { accessToken } = useAuth();

  const copyToClipboard = useCallback(async (output: ChatOutput) => {
    const text = output.content_text ?? '';
    await navigator.clipboard.writeText(text);
  }, []);

  const downloadOutput = useCallback((output: ChatOutput) => {
    const url = chatApi.downloadUrl(output.output_id);
    const a = document.createElement('a');
    a.href = url;
    a.download = output.file_name ?? `output-${output.output_id}.txt`;
    a.click();
  }, []);

  const renameOutput = useCallback(
    async (outputId: string, title: string) => {
      if (!accessToken) return;
      await chatApi.patchOutput(accessToken, outputId, title);
    },
    [accessToken],
  );

  const deleteOutput = useCallback(
    async (outputId: string) => {
      if (!accessToken) return;
      await chatApi.deleteOutput(accessToken, outputId);
    },
    [accessToken],
  );

  return { copyToClipboard, downloadOutput, renameOutput, deleteOutput };
}
