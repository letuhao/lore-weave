/**
 * Extract a human-readable message from an API error.
 * Works with standard Error objects and API JSON error responses.
 */
export function describeApiError(error: unknown, fallback = 'Something went wrong'): string {
  if (error instanceof Error) return error.message || fallback;
  if (typeof error === 'string') return error;
  if (
    error &&
    typeof error === 'object' &&
    'message' in error &&
    typeof (error as { message: unknown }).message === 'string'
  ) {
    return (error as { message: string }).message;
  }
  return fallback;
}
