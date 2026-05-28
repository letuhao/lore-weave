// Re-exports from the workspace package @loreweave/auth-client.
// The workspace package is the SSOT for auth shapes; this file is the
// frontend-game's local import point so route/component imports stay
// short ("from '@/api/auth-client'" instead of the full scope path).

export * from '@loreweave/auth-client';
