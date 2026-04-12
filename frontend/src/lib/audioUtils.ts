/**
 * Shared audio utilities for voice features.
 * Used by both Voice Mode (useVoiceChat) and Voice Assist mic (useVoiceAssistMic).
 */

/** Convert Float32Array PCM samples to a WAV Blob (16-bit mono). */
export function float32ToWavBlob(samples: Float32Array, sampleRate: number): Blob {
  const numChannels = 1;
  const bitsPerSample = 16;
  const byteRate = sampleRate * numChannels * (bitsPerSample / 8);
  const blockAlign = numChannels * (bitsPerSample / 8);
  const dataSize = samples.length * (bitsPerSample / 8);
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  // WAV header
  const writeString = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
  };
  writeString(0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitsPerSample, true);
  writeString(36, 'data');
  view.setUint32(40, dataSize, true);

  // Write samples (float32 → int16)
  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }

  return new Blob([buffer], { type: 'audio/wav' });
}

/** Send a WAV blob to the backend STT endpoint and return the transcript text. */
export async function transcribeAudio(
  audioBlob: Blob,
  sttModelRef: string,
  sttModelName: string,
  accessToken: string,
  signal?: AbortSignal,
): Promise<string> {
  const apiBase = import.meta.env.VITE_API_BASE || '';
  const params = new URLSearchParams({
    model_source: 'user_model',
    model_ref: sttModelRef,
  });
  const formData = new FormData();
  formData.append('file', audioBlob, 'audio.wav');
  // OpenAI-compatible STT APIs require a 'model' field in multipart form
  formData.append('model', sttModelName || 'whisper-1');

  const resp = await fetch(
    `${apiBase}/v1/model-registry/proxy/v1/audio/transcriptions?${params}`,
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${accessToken}` },
      body: formData,
      signal,
    },
  );

  if (!resp.ok) {
    const detail = await resp.text().catch(() => resp.statusText);
    throw new Error(`STT failed (${resp.status}): ${detail}`);
  }

  const result = await resp.json();
  return (result.text || '').trim();
}
