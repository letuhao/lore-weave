/**
 * Headphone detection utility.
 * Uses navigator.mediaDevices.enumerateDevices() to check for headphone/earphone outputs.
 * Returns true if headphones are likely connected.
 *
 * Design ref: VOICE_PIPELINE_V2.md §2.4 — enable auto-barge-in when headphones detected (no echo risk).
 */

const HEADPHONE_PATTERNS = /headphone|headset|airpod|earbud|earphone|buds/i;

export async function detectHeadphones(): Promise<boolean> {
  try {
    if (!navigator.mediaDevices?.enumerateDevices) return false;
    const devices = await navigator.mediaDevices.enumerateDevices();
    return devices.some(
      (d) => d.kind === 'audiooutput' && HEADPHONE_PATTERNS.test(d.label),
    );
  } catch {
    return false;
  }
}
