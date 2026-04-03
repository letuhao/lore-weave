import { useEffect, useState } from 'react';
import { Save, AlertTriangle, Eye, EyeOff } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { accountApi, type Profile } from './api';

export function AccountTab() {
  const { accessToken } = useAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [displayName, setDisplayName] = useState('');
  const [saving, setSaving] = useState(false);

  // Password
  const [showPwForm, setShowPwForm] = useState(false);
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [pwSaving, setPwSaving] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    accountApi.getProfile(accessToken).then((p) => {
      if (cancelled) return;
      setProfile(p);
      setDisplayName(p.display_name ?? '');
    }).catch(() => {
      if (!cancelled) toast.error('Failed to load profile');
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [accessToken]);

  async function handleSaveProfile() {
    if (!accessToken) return;
    setSaving(true);
    try {
      const updated = await accountApi.patchProfile(accessToken, { display_name: displayName });
      setProfile(updated);
      toast.success('Profile updated');
    } catch {
      toast.error('Failed to save profile');
    } finally {
      setSaving(false);
    }
  }

  async function handleChangePassword() {
    if (!accessToken) return;
    if (newPw !== confirmPw) { toast.error('Passwords do not match'); return; }
    if (newPw.length < 8) { toast.error('Password must be at least 8 characters'); return; }
    setPwSaving(true);
    try {
      await accountApi.changePassword(accessToken, { current_password: currentPw, new_password: newPw });
      toast.success('Password changed');
      setShowPwForm(false);
      setCurrentPw(''); setNewPw(''); setConfirmPw('');
    } catch (e) {
      toast.error((e as Error).message || 'Failed to change password');
    } finally {
      setPwSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-12 animate-pulse rounded-md bg-card" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-0">
      {/* Profile section */}
      <div className="border-b py-5">
        <h2 className="text-sm font-semibold">Account</h2>
        <p className="mb-4 text-xs text-muted-foreground">Manage your profile and login credentials.</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs font-medium">Display Name</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium">Email</label>
            <input
              type="email"
              value={profile?.email ?? ''}
              disabled
              className="h-9 w-full rounded-md border bg-background px-3 text-[13px] text-muted-foreground"
            />
            {profile && !profile.email_verified && (
              <p className="mt-1 text-[10px] text-yellow-500">Email not verified</p>
            )}
          </div>
        </div>
        <div className="mt-4 flex items-center justify-between">
          <button
            onClick={() => setShowPwForm(!showPwForm)}
            className="rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-secondary"
          >
            Change Password
          </button>
          <button
            onClick={handleSaveProfile}
            disabled={saving || displayName === (profile?.display_name ?? '')}
            className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:brightness-110 disabled:opacity-50"
          >
            <Save className="h-3 w-3" />
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>

      {/* Change password form */}
      {showPwForm && (
        <div className="border-b py-5">
          <h2 className="mb-3 text-sm font-semibold">Change Password</h2>
          <div className="max-w-sm space-y-3">
            <div>
              <label className="mb-1 block text-xs font-medium">Current Password</label>
              <div className="relative">
                <input
                  type={showCurrent ? 'text' : 'password'}
                  value={currentPw}
                  onChange={(e) => setCurrentPw(e.target.value)}
                  autoComplete="current-password"
                  className="h-9 w-full rounded-md border bg-background px-3 pr-9 font-mono text-[13px] tracking-wider focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
                />
                <button onClick={() => setShowCurrent(!showCurrent)} className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground" aria-label="Toggle password visibility">
                  {showCurrent ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                </button>
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium">New Password</label>
              <div className="relative">
                <input
                  type={showNew ? 'text' : 'password'}
                  value={newPw}
                  onChange={(e) => setNewPw(e.target.value)}
                  autoComplete="new-password"
                  className="h-9 w-full rounded-md border bg-background px-3 pr-9 font-mono text-[13px] tracking-wider focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
                />
                <button onClick={() => setShowNew(!showNew)} className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground" aria-label="Toggle password visibility">
                  {showNew ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                </button>
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium">Confirm New Password</label>
              <input
                type="password"
                value={confirmPw}
                onChange={(e) => setConfirmPw(e.target.value)}
                autoComplete="new-password"
                className={cn(
                  'h-9 w-full rounded-md border bg-background px-3 font-mono text-[13px] tracking-wider focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30',
                  confirmPw && confirmPw !== newPw && 'border-destructive',
                )}
              />
            </div>
            <button
              onClick={handleChangePassword}
              disabled={pwSaving || !currentPw || !newPw || newPw !== confirmPw}
              className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
            >
              {pwSaving ? 'Changing...' : 'Update Password'}
            </button>
          </div>
        </div>
      )}

      {/* Danger zone */}
      <div className="py-5">
        <h2 className="text-sm font-semibold text-destructive">Danger Zone</h2>
        <p className="mb-4 text-xs text-muted-foreground">Irreversible actions. Be careful.</p>
        <div className="flex items-center justify-between rounded-md border border-destructive/20 px-4 py-3">
          <div>
            <span className="text-[13px] font-medium">Delete Account</span>
            <p className="mt-0.5 text-[11px] text-muted-foreground">Permanently delete your account and all data. This cannot be undone.</p>
          </div>
          <button
            disabled
            className="flex items-center gap-1.5 rounded-md border border-destructive/30 px-3 py-1.5 text-xs font-medium text-destructive opacity-50"
            title="Account deletion is not yet available"
          >
            <AlertTriangle className="h-3 w-3" />
            Delete Account
          </button>
        </div>
      </div>
    </div>
  );
}
