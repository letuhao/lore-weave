import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import {
  fetchPublicProfile,
  fetchAuthorStats,
  fetchTranslatorStats,
  followUser,
  unfollowUser,
} from '@/features/profile/api';
import type { PublicProfile, AuthorStats, TranslatorStats } from '@/features/profile/api';
import { ProfileHeader } from '@/features/profile/ProfileHeader';
import { StatsRow } from '@/features/profile/StatsRow';
import { AchievementBar } from '@/features/profile/AchievementBar';
import { BooksTab } from '@/features/profile/BooksTab';
import { TranslationsTab } from '@/features/profile/TranslationsTab';
import { StubTab } from '@/features/profile/StubTab';

type Tab = 'books' | 'translations' | 'wiki' | 'reviews';

export function ProfilePage() {
  const { userId } = useParams<{ userId: string }>();
  const { t } = useTranslation('profile');
  const { user, accessToken } = useAuth();

  const [profile, setProfile] = useState<PublicProfile | null>(null);
  const [authorStats, setAuthorStats] = useState<AuthorStats | null>(null);
  const [translatorStats, setTranslatorStats] = useState<TranslatorStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('books');
  const [followLoading, setFollowLoading] = useState(false);

  const isSelf = user?.user_id === userId;

  useEffect(() => {
    if (!userId) return;
    setLoading(true);
    setError(null);

    Promise.all([
      fetchPublicProfile(userId, accessToken),
      fetchAuthorStats(userId),
      fetchTranslatorStats(userId).catch(() => null),
    ])
      .then(([prof, author, translator]) => {
        setProfile(prof);
        setAuthorStats(author);
        setTranslatorStats(translator);
      })
      .catch(() => setError(t('errorLoading')))
      .finally(() => setLoading(false));
  }, [userId, accessToken]);

  const handleFollow = useCallback(async () => {
    if (!userId || !accessToken) return;
    setFollowLoading(true);
    setProfile((p) =>
      p ? { ...p, is_following: true, follower_count: p.follower_count + 1 } : p,
    );
    try {
      await followUser(userId, accessToken);
    } catch {
      setProfile((p) =>
        p ? { ...p, is_following: false, follower_count: Math.max(0, p.follower_count - 1) } : p,
      );
      toast.error(t('followError'));
    }
    setFollowLoading(false);
  }, [userId, accessToken, t]);

  const handleUnfollow = useCallback(async () => {
    if (!userId || !accessToken) return;
    setFollowLoading(true);
    setProfile((p) =>
      p ? { ...p, is_following: false, follower_count: Math.max(0, p.follower_count - 1) } : p,
    );
    try {
      await unfollowUser(userId, accessToken);
    } catch {
      setProfile((p) =>
        p ? { ...p, is_following: true, follower_count: p.follower_count + 1 } : p,
      );
      toast.error(t('unfollowError'));
    }
    setFollowLoading(false);
  }, [userId, accessToken, t]);

  if (loading) {
    return (
      <div className="max-w-[900px] mx-auto px-8 py-12">
        <div className="animate-pulse space-y-4">
          <div className="flex gap-6">
            <div className="w-20 h-20 rounded-full bg-[var(--secondary)]" />
            <div className="flex-1 space-y-2">
              <div className="h-6 w-48 bg-[var(--secondary)] rounded" />
              <div className="h-4 w-72 bg-[var(--secondary)] rounded" />
            </div>
          </div>
          <div className="h-20 bg-[var(--secondary)] rounded-lg" />
        </div>
      </div>
    );
  }

  if (error || !profile || !authorStats) {
    return (
      <div className="max-w-[900px] mx-auto px-8 py-12 text-center">
        <p className="text-[var(--muted-fg)]">{error || t('userNotFound')}</p>
      </div>
    );
  }

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: 'books', label: t('tabs.books'), count: authorStats.total_books },
    {
      key: 'translations',
      label: t('tabs.translations'),
      count: translatorStats?.total_chapters_done ?? 0,
    },
    { key: 'wiki', label: t('tabs.wiki') },
    { key: 'reviews', label: t('tabs.reviews') },
  ];

  return (
    <div className="max-w-[900px] mx-auto px-8 py-6">
      <ProfileHeader
        profile={profile}
        isSelf={isSelf}
        onFollow={handleFollow}
        onUnfollow={handleUnfollow}
        followLoading={followLoading}
      />

      <StatsRow
        author={authorStats}
        translator={translatorStats}
        followerCount={profile.follower_count}
      />

      <AchievementBar
        author={authorStats}
        translator={translatorStats}
        followerCount={profile.follower_count}
      />

      {/* Tabs */}
      <div className="flex gap-0 border-b border-[var(--border)] mb-4">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2.5 text-[13px] font-medium border-b-2 transition-colors ${
              activeTab === tab.key
                ? 'text-[var(--primary)] border-[var(--primary)]'
                : 'text-[var(--muted-fg)] border-transparent hover:text-[var(--foreground)]'
            }`}
          >
            {tab.label}
            {tab.count !== undefined && tab.count > 0 && (
              <span className="ml-1 text-[var(--muted-fg)]">({tab.count})</span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'books' && <BooksTab userId={userId!} />}
      {activeTab === 'translations' && <TranslationsTab translator={translatorStats} />}
      {activeTab === 'wiki' && <StubTab label={t('tabs.wiki')} />}
      {activeTab === 'reviews' && <StubTab label={t('tabs.reviews')} />}
    </div>
  );
}
