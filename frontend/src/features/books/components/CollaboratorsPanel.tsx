import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { UserPlus, X } from 'lucide-react';
import { useCollaborators } from '@/features/books/hooks/useCollaborators';
import type { CollaboratorRole } from '@/features/books/api';
import { Skeleton } from '@/components/shared/Skeleton';

const ROLES: CollaboratorRole[] = ['view', 'edit', 'manage'];
type ApiError = Error & { status?: number; code?: string };

/** E0-5 — owner-only "Collaborators" panel (mounted on the Sharing tab). Invite by
 *  email, change a role, or revoke. Renders nothing for a non-owner (the hook gates
 *  on the owner-only endpoints' 403). View-only — all logic lives in the hook. */
export function CollaboratorsPanel({ bookId }: { bookId: string }) {
  const { t } = useTranslation('books');
  const { collaborators, loading, forbidden, error, invite, changeRole, remove } = useCollaborators(bookId);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<CollaboratorRole>('view');
  const [inviting, setInviting] = useState(false);

  if (forbidden) return null; // not the owner — panel is owner-only

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    const addr = email.trim();
    if (!addr || inviting) return;
    setInviting(true);
    try {
      await invite(addr, role);
      toast.success(t('collaborators.invited', { email: addr }));
      setEmail('');
    } catch (err) {
      const ae = err as ApiError;
      const msg =
        ae.status === 404 ? t('collaborators.no_such_user')
        : ae.code === 'CANNOT_GRANT_OWNER' ? t('collaborators.cannot_grant_owner')
        : ae.message || t('collaborators.invite_failed');
      toast.error(msg);
    } finally {
      setInviting(false);
    }
  };

  const wrap = (fn: Promise<void>) => fn.catch((e) => toast.error((e as Error).message));

  return (
    <section className="space-y-3">
      <div>
        <h3 className="text-sm font-medium">{t('collaborators.title')}</h3>
        <p className="text-xs text-muted-foreground">{t('collaborators.subtitle')}</p>
      </div>

      <form onSubmit={handleInvite} className="flex flex-wrap items-center gap-2">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={t('collaborators.email_placeholder')}
          aria-label={t('collaborators.email_placeholder')}
          className="flex-1 min-w-[12rem] rounded-md border bg-background px-3 py-2 text-sm"
        />
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as CollaboratorRole)}
          aria-label={t('collaborators.role_label')}
          className="rounded-md border bg-background px-2 py-2 text-sm"
        >
          {ROLES.map((r) => <option key={r} value={r}>{t(`collaborators.roles.${r}`)}</option>)}
        </select>
        <button
          type="submit"
          disabled={inviting || !email.trim()}
          className="inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm hover:bg-secondary disabled:opacity-50"
        >
          <UserPlus className="h-3.5 w-3.5" /> {t('collaborators.invite')}
        </button>
      </form>

      {error && <p className="text-sm text-destructive">{error}</p>}
      {loading ? (
        <Skeleton className="h-8 w-full" />
      ) : collaborators.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('collaborators.empty')}</p>
      ) : (
        <ul className="divide-y rounded-md border">
          {collaborators.map((c) => (
            <li key={c.user_id} className="flex items-center gap-2 px-3 py-2">
              <span className="flex-1 truncate text-sm">
                {c.display_name || t('collaborators.unnamed', { id: c.user_id.slice(0, 8) })}
              </span>
              <select
                value={c.role}
                onChange={(e) => void wrap(changeRole(c.user_id, e.target.value as CollaboratorRole))}
                aria-label={t('collaborators.role_label')}
                className="rounded-md border bg-background px-2 py-1 text-sm"
              >
                {ROLES.map((r) => <option key={r} value={r}>{t(`collaborators.roles.${r}`)}</option>)}
              </select>
              <button
                onClick={() => void wrap(remove(c.user_id))}
                aria-label={t('collaborators.remove')}
                title={t('collaborators.remove')}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-destructive"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
