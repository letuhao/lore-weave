import { useState, useEffect } from 'react';
import { Globe, Lock, Link2, RefreshCw, Copy, Check } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { Skeleton } from '@/components/shared/Skeleton';
import { cn } from '@/lib/utils';

type Visibility = 'private' | 'unlisted' | 'public';

const VISIBILITY_OPTIONS: { value: Visibility; label: string; icon: typeof Globe; desc: string }[] = [
  { value: 'private', label: 'Private', icon: Lock, desc: 'Only you can see this book' },
  { value: 'unlisted', label: 'Unlisted', icon: Link2, desc: 'Anyone with the link can read' },
  { value: 'public', label: 'Public', icon: Globe, desc: 'Visible in the public catalog' },
];

export function SharingTab({ bookId }: { bookId: string }) {
  const { accessToken } = useAuth();
  const [visibility, setVisibility] = useState<Visibility>('private');
  const [unlistedToken, setUnlistedToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    booksApi.getSharing(accessToken, bookId)
      .then((data) => {
        setVisibility(data.visibility);
        setUnlistedToken(data.unlisted_access_token ?? null);
      })
      .catch(() => toast.error('Failed to load sharing settings'))
      .finally(() => setLoading(false));
  }, [accessToken, bookId]);

  const handleVisibilityChange = async (v: Visibility) => {
    if (!accessToken || saving) return;
    setSaving(true);
    try {
      const result = await booksApi.patchSharing(accessToken, bookId, { visibility: v }) as { visibility: Visibility; unlisted_access_token?: string };
      setVisibility(result.visibility);
      setUnlistedToken(result.unlisted_access_token ?? null);
      toast.success(`Visibility set to ${v}`);
    } catch {
      toast.error('Failed to update visibility');
    } finally {
      setSaving(false);
    }
  };

  const handleRotateToken = async () => {
    if (!accessToken || saving) return;
    setSaving(true);
    try {
      const result = await booksApi.patchSharing(accessToken, bookId, { rotate_unlisted_token: true }) as { unlisted_access_token?: string };
      setUnlistedToken(result.unlisted_access_token ?? null);
      toast.success('Link token rotated');
    } catch {
      toast.error('Failed to rotate token');
    } finally {
      setSaving(false);
    }
  };

  const handleCopy = () => {
    if (!unlistedToken) return;
    const url = `${window.location.origin}/read/${unlistedToken}`;
    navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading) {
    return (
      <div className="space-y-3 p-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  return (
    <div className="max-w-lg space-y-6 p-6">
      <div>
        <h3 className="text-sm font-semibold">Visibility</h3>
        <p className="mb-3 text-xs text-muted-foreground">Control who can see and read this book.</p>

        <div className="space-y-2">
          {VISIBILITY_OPTIONS.map(({ value, label, icon: Icon, desc }) => (
            <button
              key={value}
              onClick={() => handleVisibilityChange(value)}
              disabled={saving}
              className={cn(
                'flex w-full items-center gap-3 rounded-lg border px-4 py-3 text-left transition-colors',
                visibility === value
                  ? 'border-primary bg-primary/5'
                  : 'hover:bg-secondary',
              )}
            >
              <div className={cn(
                'flex h-8 w-8 items-center justify-center rounded-full',
                visibility === value ? 'bg-primary/15 text-primary' : 'bg-secondary text-muted-foreground',
              )}>
                <Icon className="h-4 w-4" />
              </div>
              <div>
                <span className={cn('text-sm font-medium', visibility === value && 'text-primary')}>
                  {label}
                </span>
                <p className="text-[11px] text-muted-foreground">{desc}</p>
              </div>
              {visibility === value && (
                <Check className="ml-auto h-4 w-4 text-primary" />
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Unlisted link section */}
      {visibility === 'unlisted' && unlistedToken && (
        <div className="rounded-lg border bg-card p-4">
          <h4 className="mb-2 text-xs font-semibold">Shareable Link</h4>
          <div className="flex items-center gap-2">
            <div className="flex-1 truncate rounded-md border bg-background px-3 py-2 font-mono text-[11px] text-muted-foreground">
              {window.location.origin}/read/{unlistedToken}
            </div>
            <button
              onClick={handleCopy}
              className="inline-flex items-center gap-1 rounded-md border px-2.5 py-2 text-xs font-medium hover:bg-secondary"
            >
              {copied ? <Check className="h-3 w-3 text-green-500" /> : <Copy className="h-3 w-3" />}
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
          <button
            onClick={handleRotateToken}
            disabled={saving}
            className="mt-2 inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
          >
            <RefreshCw className="h-3 w-3" />
            Rotate link (invalidates old link)
          </button>
        </div>
      )}
    </div>
  );
}
