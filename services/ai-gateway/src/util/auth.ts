/**
 * Length-independent constant-time string compare for the internal service token.
 * Avoids the timing side-channel of `!==` on the shared secret (AIGW-LOW: noted by
 * the public-MCP P0 spike). Compares every position regardless of length so neither
 * the value nor the length leaks via early-exit timing.
 */
export function constantTimeEquals(a: string, b: string): boolean {
  const len = Math.max(a.length, b.length);
  let diff = a.length ^ b.length;
  for (let i = 0; i < len; i++) {
    diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  }
  return diff === 0;
}
