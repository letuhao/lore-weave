// W6 — a tiny, provider-free read of the current user's id for tenancy-tier
// derivation (system vs user vs public). The auth layer persists the profile under
// `lw_user` in localStorage (src/auth.tsx); reading it directly keeps the motif
// panels renderable WITHOUT an AuthProvider in the parent tree (the existing
// CompositionPanel unit test mounts panels with no AuthProvider). The server stays
// the source of truth — this id is only used to GROUP rows in the UI; every
// write/read is still authorized server-side by the JWT.
export function currentUserId(): string | null {
  try {
    const raw = localStorage.getItem('lw_user');
    if (!raw) return null;
    const u = JSON.parse(raw) as { user_id?: string };
    return u.user_id ?? null;
  } catch {
    return null;
  }
}
