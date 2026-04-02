import { useCallback, useEffect, useState } from 'react';
import { Check, Copy, Eye, EyeOff, Globe, Link2, RefreshCw, Shield } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

type Visibility = 'private' | 'unlisted' | 'public';

interface SharingTabProps {
  bookId: string;
}

const VISIBILITY_OPTIONS: {
  value: Visibility;
  label: string;
  description: string;
  icon: React.ReactNode;
}[] = [
  {
    value: 'private',
    label: 'Private',
    description: 'Only you can access this book.',
    icon: <Shield className="h-4 w-4" />,
  },
  {
    value: 'unlisted',
    label: 'Unlisted',
    description: 'Anyone with the link can read this book. Not listed in public catalog.',
    icon: <EyeOff className="h-4 w-4" />,
  },
  {
    value: 'public',
    label: 'Public',
    description: 'Listed in the public catalog. Anyone can discover and read this book.',
    icon: <Globe className="h-4 w-4" />,
  },
];

export function SharingTab({ bookId }: SharingTabProps) {
  const { accessToken } = useAuth();
  const [visibility, setVisibility] = useState<Visibility>('private');
  const [unlistedToken, setUnlistedToken] = useState<string | undefined>();
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isRotating, setIsRotating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [savedVisibility, setSavedVisibility] = useState<Visibility>('private');

  // ── Load current sharing policy ─────────────────────────────────────────────

  const load = useCallback(async () => {
    if (!accessToken || !bookId) return;
    setIsLoading(true);
    try {
      const res = await booksApi.getSharing(accessToken, bookId);
      setVisibility(res.visibility);
      setSavedVisibility(res.visibility);
      setUnlistedToken(res.unlisted_access_token);
      setDirty(false);
    } catch (e) {
      toast.error(`Failed to load sharing settings: ${(e as Error).message}`);
    } finally {
      setIsLoading(false);
    }
  }, [accessToken, bookId]);

  useEffect(() => {
    void load();
  }, [load]);

  // ── Save visibility ─────────────────────────────────────────────────────────

  async function handleSave() {
    if (!accessToken || !bookId) return;
    setIsSaving(true);
    try {
      const res = await booksApi.patchSharing(accessToken, bookId, { visibility });
      const result = res as { visibility: Visibility; unlisted_access_token?: string };
      setVisibility(result.visibility);
      setSavedVisibility(result.visibility);
      setUnlistedToken(result.unlisted_access_token);
      setDirty(false);
      toast.success(
        result.visibility === 'private'
          ? 'Book is now private'
          : result.visibility === 'unlisted'
            ? 'Book is now unlisted — share the link below'
            : 'Book is now public',
      );
    } catch (e) {
      toast.error(`Failed to save: ${(e as Error).message}`);
    } finally {
      setIsSaving(false);
    }
  }

  // ── Rotate unlisted token ───────────────────────────────────────────────────

  async function handleRotateToken() {
    if (!accessToken || !bookId) return;
    setIsRotating(true);
    try {
      const res = await booksApi.patchSharing(accessToken, bookId, {
        visibility: 'unlisted',
        rotate_unlisted_token: true,
      });
      const result = res as { visibility: Visibility; unlisted_access_token?: string };
      setUnlistedToken(result.unlisted_access_token);
      toast.success('Link rotated — the old link no longer works');
    } catch (e) {
      toast.error(`Failed to rotate link: ${(e as Error).message}`);
    } finally {
      setIsRotating(false);
    }
  }

  // ── Copy link ───────────────────────────────────────────────────────────────

  async function handleCopyLink() {
    if (!unlistedToken) return;
    const url = `${window.location.origin}/s/${unlistedToken}`;
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
    toast.success('Link copied to clipboard');
  }

  // ── Select visibility ───────────────────────────────────────────────────────

  function selectVisibility(v: Visibility) {
    setVisibility(v);
    setDirty(v !== savedVisibility);
  }

  // ── Loading skeleton ────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="max-w-xl space-y-4">
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 animate-pulse rounded-lg border bg-muted/30" />
          ))}
        </div>
      </div>
    );
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  const unlistedUrl = unlistedToken ? `${window.location.origin}/s/${unlistedToken}` : '';

  return (
    <div className="max-w-xl space-y-6">
      {/* Visibility selector */}
      <div>
        <h3 className="mb-1 text-sm font-semibold text-foreground">Visibility</h3>
        <p className="mb-3 text-xs text-muted-foreground">
          Control who can access this book.
        </p>

        <div className="space-y-2">
          {VISIBILITY_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => selectVisibility(opt.value)}
              className={cn(
                'flex w-full items-start gap-3 rounded-lg border px-4 py-3 text-left transition-colors',
                visibility === opt.value
                  ? 'border-ring bg-ring/5 shadow-sm'
                  : 'border-border hover:border-border/80 hover:bg-muted/30',
              )}
            >
              <div
                className={cn(
                  'mt-0.5 rounded-md p-1.5',
                  visibility === opt.value
                    ? 'bg-primary/10 text-primary'
                    : 'bg-muted text-muted-foreground',
                )}
              >
                {opt.icon}
              </div>
              <div className="min-w-0 flex-1">
                <p
                  className={cn(
                    'text-sm font-medium',
                    visibility === opt.value ? 'text-foreground' : 'text-foreground/80',
                  )}
                >
                  {opt.label}
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">{opt.description}</p>
              </div>
              {visibility === opt.value && (
                <div className="mt-0.5 rounded-full bg-primary p-0.5 text-primary-foreground">
                  <Check className="h-3 w-3" />
                </div>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Save button */}
      {dirty && (
        <Button onClick={handleSave} disabled={isSaving} className="gap-1.5">
          {isSaving ? 'Saving\u2026' : 'Save Changes'}
        </Button>
      )}

      {/* Unlisted link section */}
      {savedVisibility === 'unlisted' && unlistedToken && (
        <div className="space-y-3 rounded-lg border border-border bg-card p-4">
          <div className="flex items-center gap-2">
            <Link2 className="h-4 w-4 text-muted-foreground" />
            <h4 className="text-sm font-medium text-foreground">Shareable Link</h4>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex-1 truncate rounded-md border bg-background px-3 py-2 font-mono text-xs text-muted-foreground">
              {unlistedUrl}
            </div>
            <Button
              size="sm"
              variant="outline"
              className="shrink-0 gap-1.5"
              onClick={handleCopyLink}
            >
              {copied ? (
                <>
                  <Check className="h-3.5 w-3.5 text-emerald-500" />
                  Copied
                </>
              ) : (
                <>
                  <Copy className="h-3.5 w-3.5" />
                  Copy
                </>
              )}
            </Button>
          </div>

          <div className="flex items-center justify-between border-t border-border pt-3">
            <p className="text-[11px] text-muted-foreground">
              Anyone with this link can read the book. Rotating generates a new link and invalidates the old one.
            </p>
            <Button
              size="sm"
              variant="ghost"
              className="shrink-0 gap-1.5 text-xs text-muted-foreground"
              onClick={handleRotateToken}
              disabled={isRotating}
            >
              <RefreshCw className={cn('h-3.5 w-3.5', isRotating && 'animate-spin')} />
              {isRotating ? 'Rotating\u2026' : 'Rotate'}
            </Button>
          </div>
        </div>
      )}

      {/* Public info */}
      {savedVisibility === 'public' && (
        <div className="flex items-start gap-3 rounded-lg border border-border bg-card p-4">
          <Eye className="mt-0.5 h-4 w-4 text-emerald-500" />
          <div>
            <p className="text-sm font-medium text-foreground">This book is publicly listed</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              It appears in the public catalog at{' '}
              <a href="/browse" className="underline hover:text-foreground">
                /browse
              </a>{' '}
              and can be discovered by anyone.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
