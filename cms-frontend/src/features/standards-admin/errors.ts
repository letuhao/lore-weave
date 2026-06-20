// Normalize a write/read error into a user-facing message. The CMS login
// currently yields a normal user token (the admin-session exchange isn't built
// yet), so a 401/403 on a write is the expected "not an admin token" case.
export function describeError(err: unknown): string {
  const status = (err as { status?: number } | null)?.status;
  if (status === 401 || status === 403) {
    return "Admin session required — your token isn't an admin token.";
  }
  if (err instanceof Error && err.message) {
    return err.message;
  }
  return 'Something went wrong.';
}
