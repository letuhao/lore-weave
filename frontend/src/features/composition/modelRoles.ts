/** The Book tier of the model cascade, in the form the platform declares it prefers.
 *
 * `work.settings` can express a per-role model two ways:
 *
 *     settings.model_roles            {role: {model_ref, model_source}}   ← PREFERRED
 *     settings.default_model_ref      a scalar meaning role "chat"        ← legacy
 *     settings.critic_model_ref       a scalar meaning role "critic"      ← legacy
 *
 * Measured 2026-08-03: the map had ZERO writers repo-wide. This view — the only UI that sets a
 * critic — wrote the scalars, so the branch the backend prefers was dead in production.
 *
 * That mattered beyond tidiness. `ModelRole` is "the one canonical closed set … shared as the
 * key vocabulary across all three model stores" and has SIX members (chat, composer, planner,
 * embedding, rerank, critic). Two scalars can express two of them, so the Book tier of a
 * six-role cascade could hold two roles and the shape designed to hold all six was never
 * written.
 *
 * Mirrors `composition-service/app/engine/model_roles.py`. Kept small and total on purpose:
 * both sides read the map first and fall back to the scalar, and a divergence here would show
 * up as a setting that saves and then appears to revert.
 */

export type RoleModel = { model_ref: string; model_source: string };

/** The two roles that predate the map, and the scalars they were stored in. A third role never
 *  had a scalar pair — which is the reason the map exists. */
export const LEGACY_SCALARS: Record<string, [refKey: string, sourceKey: string]> = {
  chat: ['default_model_ref', 'default_model_source'],
  critic: ['critic_model_ref', 'critic_model_source'],
};

type Settings = Record<string, unknown>;

/** The current ref for one role — map first, then the legacy scalar. `''` when unset. */
export function roleRef(settings: Settings, role: string): string {
  const map = settings.model_roles;
  if (map && typeof map === 'object') {
    const got = (map as Record<string, unknown>)[role];
    if (got && typeof got === 'object') {
      const ref = (got as Record<string, unknown>).model_ref;
      if (typeof ref === 'string' && ref) return ref;
    }
  }
  const legacy = LEGACY_SCALARS[role];
  const scalar = legacy ? settings[legacy[0]] : undefined;
  return typeof scalar === 'string' ? scalar : '';
}

/** The patch that sets — or clears — one role, in the map form.
 *
 * Clearing removes the role from the map AND nulls the legacy pair. Both, because the reader
 * falls back to the scalar: dropping only the map entry would make the setting appear to
 * un-clear itself on the next read, which is worse than never having been clearable.
 */
export function patchForRole(
  settings: Settings,
  role: string,
  modelRef: string,
  modelSource = 'user_model',
): Record<string, unknown> {
  const current: Record<string, RoleModel> = { ...((settings.model_roles as Record<string, RoleModel>) || {}) };
  const patch: Record<string, unknown> = {};
  if (modelRef) {
    current[role] = { model_ref: modelRef, model_source: modelSource };
  } else {
    delete current[role];
    const legacy = LEGACY_SCALARS[role];
    if (legacy) {
      patch[legacy[0]] = null;
      patch[legacy[1]] = null;
    }
  }
  patch.model_roles = current;
  return patch;
}
