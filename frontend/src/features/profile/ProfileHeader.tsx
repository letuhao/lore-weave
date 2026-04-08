import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import type { PublicProfile } from './api';

type Props = {
  profile: PublicProfile;
  isSelf: boolean;
  onFollow: () => void;
  onUnfollow: () => void;
  followLoading: boolean;
};

function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((w) => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2) || '?';
}

export function ProfileHeader({ profile, isSelf, onFollow, onUnfollow, followLoading }: Props) {
  const { t } = useTranslation('profile');
  const joinDate = new Date(profile.created_at).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'long',
  });

  return (
    <div className="flex gap-6 mb-6">
      {/* Avatar */}
      {profile.avatar_url ? (
        <img
          src={profile.avatar_url}
          alt={profile.display_name}
          className="w-20 h-20 rounded-full border-[3px] border-[var(--primary)] object-cover flex-shrink-0"
        />
      ) : (
        <div className="w-20 h-20 rounded-full bg-[var(--primary-muted)] text-[var(--primary)] text-[28px] font-bold flex items-center justify-center flex-shrink-0 border-[3px] border-[var(--primary)]">
          {initials(profile.display_name || '?')}
        </div>
      )}

      <div className="flex-1 min-w-0">
        {/* Name + badges */}
        <div className="flex items-center gap-2.5 mb-1 flex-wrap">
          <h1 className="text-[22px] font-bold truncate">{profile.display_name || t('anonymous')}</h1>
        </div>

        {/* Bio */}
        {profile.bio && (
          <p className="text-[13px] text-[var(--muted-fg)] mb-2.5 leading-relaxed">{profile.bio}</p>
        )}

        {/* Languages + join date */}
        <div className="flex items-center gap-3 text-xs text-[var(--muted-fg)] flex-wrap">
          {profile.languages.length > 0 && <span>{profile.languages.join(', ')}</span>}
          {profile.languages.length > 0 && <span className="text-[var(--border)]">&middot;</span>}
          <span>{t('joined', { date: joinDate })}</span>
          <span className="text-[var(--border)]">&middot;</span>
          <span>
            <strong className="text-[var(--foreground)]">{profile.follower_count}</strong>{' '}
            {t('followers')}
          </span>
          <span className="text-[var(--border)]">&middot;</span>
          <span>
            <strong className="text-[var(--foreground)]">{profile.following_count}</strong>{' '}
            {t('following')}
          </span>
        </div>

        {/* Actions */}
        <div className="flex gap-2 mt-3">
          {isSelf ? (
            <Link
              to="/settings"
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-md text-xs font-medium border border-[var(--border)] text-[var(--foreground)] hover:bg-[var(--secondary)] transition-colors"
            >
              {t('editProfile')}
            </Link>
          ) : (
            <button
              onClick={profile.is_following ? onUnfollow : onFollow}
              disabled={followLoading}
              className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-md text-xs font-medium transition-colors disabled:opacity-50 ${
                profile.is_following
                  ? 'border border-[var(--border)] text-[var(--foreground)] hover:bg-[var(--secondary)]'
                  : 'bg-[var(--primary)] text-[var(--primary-fg)]'
              }`}
            >
              {profile.is_following ? t('unfollow') : t('follow')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
