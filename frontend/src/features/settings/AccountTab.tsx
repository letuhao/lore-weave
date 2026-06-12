import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Save, AlertTriangle, Eye, EyeOff, Mail, CheckCircle } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { ConfirmDialog } from '@/components/shared';
import { accountApi, type Profile } from './api';

export function AccountTab() {
  const { t } = useTranslation('settings');
  const { accessToken, updateUser } = useAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [displayName, setDisplayName] = useState('');
  const [saving, setSaving] = useState(false);

  // Account deletion
  const [deleteOpen, setDeleteOpen] = useState(false);
  const handleDeleteAccount = async () => {
    if (!accessToken) return;
    try {
      await accountApi.deleteAccount(accessToken);
      toast.success(t('account.toast.deleted'));
      localStorage.removeItem('lw_auth');
      window.location.href = '/login';
    } catch {
      toast.error(t('account.toast.delete_failed'));
    }
  };

  // Password
  const [showPwForm, setShowPwForm] = useState(false);
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [pwSaving, setPwSaving] = useState(false);

  // Email verification
  const [verifyStep, setVerifyStep] = useState<'idle' | 'sent' | 'confirm'>('idle');
  const [verifyToken, setVerifyToken] = useState('');
  const [verifySending, setVerifySending] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    accountApi.getProfile(accessToken).then((p) => {
      if (cancelled) return;
      setProfile(p);
      setDisplayName(p.display_name ?? '');
    }).catch(() => {
      if (!cancelled) toast.error(t('account.toast.load_failed'));
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
      updateUser({ display_name: updated.display_name });
      toast.success(t('account.toast.updated'));
    } catch {
      toast.error(t('account.toast.save_failed'));
    } finally {
      setSaving(false);
    }
  }

  async function handleChangePassword() {
    if (!accessToken) return;
    if (newPw !== confirmPw) { toast.error(t('account.toast.pw_mismatch')); return; }
    if (newPw.length < 8) { toast.error(t('account.toast.pw_too_short')); return; }
    setPwSaving(true);
    try {
      await accountApi.changePassword(accessToken, { current_password: currentPw, new_password: newPw });
      toast.success(t('account.toast.pw_changed'));
      setShowPwForm(false);
      setCurrentPw(''); setNewPw(''); setConfirmPw('');
    } catch (e) {
      toast.error((e as Error).message || t('account.toast.pw_change_failed'));
    } finally {
      setPwSaving(false);
    }
  }

  async function handleRequestVerify() {
    if (!accessToken) return;
    setVerifySending(true);
    try {
      await accountApi.requestVerifyEmail(accessToken);
      setVerifyStep('sent');
      toast.success(t('account.toast.verify_sent'));
    } catch (e) {
      toast.error((e as Error).message || t('account.toast.verify_send_failed'));
    } finally {
      setVerifySending(false);
    }
  }

  async function handleConfirmVerify() {
    if (!verifyToken.trim()) return;
    setVerifySending(true);
    try {
      await accountApi.confirmVerifyEmail(verifyToken.trim());
      setProfile((p) => p ? { ...p, email_verified: true } : p);
      setVerifyStep('idle');
      setVerifyToken('');
      toast.success(t('account.toast.email_verified'));
    } catch (e) {
      toast.error((e as Error).message || t('account.toast.verify_failed'));
    } finally {
      setVerifySending(false);
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
        <h2 className="text-sm font-semibold">{t('account.heading')}</h2>
        <p className="mb-4 text-xs text-muted-foreground">{t('account.subtitle')}</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs font-medium">{t('account.display_name')}</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium">{t('account.email')}</label>
            <input
              type="email"
              value={profile?.email ?? ''}
              disabled
              className="h-9 w-full rounded-md border bg-background px-3 text-[13px] text-muted-foreground"
            />
            {profile?.email_verified ? (
              <p className="mt-1 flex items-center gap-1 text-[10px] text-green-500">
                <CheckCircle className="h-3 w-3" /> {t('account.verified')}
              </p>
            ) : profile ? (
              <div className="mt-1.5">
                {verifyStep === 'idle' && (
                  <button
                    onClick={handleRequestVerify}
                    disabled={verifySending}
                    className="flex items-center gap-1 text-[10px] font-medium text-yellow-500 hover:text-yellow-400"
                  >
                    <Mail className="h-3 w-3" />
                    {verifySending ? t('account.sending') : t('account.verify_email')}
                  </button>
                )}
                {verifyStep === 'sent' && (
                  <div className="space-y-1.5">
                    <p className="text-[10px] text-green-500">{t('account.verify_sent_line')}</p>
                    <button onClick={() => setVerifyStep('confirm')} className="text-[10px] font-medium text-primary hover:underline">
                      {t('account.enter_token')}
                    </button>
                  </div>
                )}
                {verifyStep === 'confirm' && (
                  <div className="flex items-center gap-1.5">
                    <input
                      type="text"
                      value={verifyToken}
                      onChange={(e) => setVerifyToken(e.target.value)}
                      placeholder={t('account.token_placeholder')}
                      autoComplete="off"
                      className="h-7 w-48 rounded border bg-background px-2 text-[11px] focus:border-ring focus:outline-none"
                    />
                    <button
                      onClick={handleConfirmVerify}
                      disabled={verifySending || !verifyToken.trim()}
                      className="rounded bg-primary px-2 py-1 text-[10px] font-medium text-primary-foreground disabled:opacity-50"
                    >
                      {verifySending ? '...' : t('account.confirm')}
                    </button>
                    <button onClick={() => { setVerifyStep('idle'); setVerifyToken(''); }} className="text-[10px] text-muted-foreground hover:text-foreground">
                      {t('account.cancel')}
                    </button>
                  </div>
                )}
              </div>
            ) : null}
          </div>
        </div>
        <div className="mt-4 flex items-center justify-between">
          <button
            onClick={() => setShowPwForm(!showPwForm)}
            className="rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-secondary"
          >
            {t('account.change_password')}
          </button>
          <button
            onClick={handleSaveProfile}
            disabled={saving || displayName === (profile?.display_name ?? '')}
            className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:brightness-110 disabled:opacity-50"
          >
            <Save className="h-3 w-3" />
            {saving ? t('account.saving') : t('account.save_changes')}
          </button>
        </div>
      </div>

      {/* Change password form */}
      {showPwForm && (
        <div className="border-b py-5">
          <h2 className="mb-3 text-sm font-semibold">{t('account.pw_heading')}</h2>
          <div className="max-w-sm space-y-3">
            <div>
              <label className="mb-1 block text-xs font-medium">{t('account.current_pw')}</label>
              <div className="relative">
                <input
                  type={showCurrent ? 'text' : 'password'}
                  value={currentPw}
                  onChange={(e) => setCurrentPw(e.target.value)}
                  autoComplete="current-password"
                  className="h-9 w-full rounded-md border bg-background px-3 pr-9 font-mono text-[13px] tracking-wider focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
                />
                <button onClick={() => setShowCurrent(!showCurrent)} className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground" aria-label={t('account.toggle_pw_aria')}>
                  {showCurrent ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                </button>
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium">{t('account.new_pw')}</label>
              <div className="relative">
                <input
                  type={showNew ? 'text' : 'password'}
                  value={newPw}
                  onChange={(e) => setNewPw(e.target.value)}
                  autoComplete="new-password"
                  className="h-9 w-full rounded-md border bg-background px-3 pr-9 font-mono text-[13px] tracking-wider focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
                />
                <button onClick={() => setShowNew(!showNew)} className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground" aria-label={t('account.toggle_pw_aria')}>
                  {showNew ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                </button>
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium">{t('account.confirm_new_pw')}</label>
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
              {pwSaving ? t('account.changing') : t('account.update_password')}
            </button>
          </div>
        </div>
      )}

      {/* Danger zone */}
      <div className="py-5">
        <h2 className="text-sm font-semibold text-destructive">{t('account.danger_zone')}</h2>
        <p className="mb-4 text-xs text-muted-foreground">{t('account.danger_subtitle')}</p>
        <div className="flex items-center justify-between rounded-md border border-destructive/20 px-4 py-3">
          <div>
            <span className="text-[13px] font-medium">{t('account.delete_account')}</span>
            <p className="mt-0.5 text-[11px] text-muted-foreground">{t('account.delete_desc')}</p>
          </div>
          <button
            onClick={() => setDeleteOpen(true)}
            className="flex items-center gap-1.5 rounded-md border border-destructive/30 px-3 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/10"
          >
            <AlertTriangle className="h-3 w-3" />
            {t('account.delete_account')}
          </button>
        </div>
      </div>
      {deleteOpen && (
        <ConfirmDialog
          open
          onOpenChange={(v) => { if (!v) setDeleteOpen(false); }}
          title={t('account.delete_dialog_title')}
          description={t('account.delete_dialog_desc')}
          confirmLabel={t('account.delete_confirm_label')}
          variant="destructive"
          onConfirm={handleDeleteAccount}
        />
      )}
    </div>
  );
}
