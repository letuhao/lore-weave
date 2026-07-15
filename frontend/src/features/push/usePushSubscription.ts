// M5 (D-MOB-4) controller — the device's push subscription lifecycle. Owns the capability gate, the
// effective on/off state (§8-S4: AND(OS-permission granted, a live subscription present)), and the
// subscribe/unsubscribe flow. CLAUDE.md MVC: the toggle view only renders + calls enable/disable.
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { pushApi, urlBase64ToUint8Array } from './api';
import { detectPushCapability, type PushCapability } from './capability';

export interface PushState {
  capability: PushCapability;
  /** Effective: a live subscription exists AND permission is granted. */
  enabled: boolean;
  busy: boolean;
  enable: () => void;
  disable: () => void;
}

async function currentSubscription(): Promise<PushSubscription | null> {
  if (!('serviceWorker' in navigator)) return null;
  const reg = await navigator.serviceWorker.getRegistration();
  return (await reg?.pushManager.getSubscription()) ?? null;
}

export function usePushSubscription(): PushState {
  const { accessToken } = useAuth();
  const [capability, setCapability] = useState<PushCapability>(() => detectPushCapability());
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);

  // Recompute effective state on mount + when the tab returns to the foreground (OS permission can
  // change in device settings while we're backgrounded — §8-S4).
  const refresh = useCallback(async () => {
    const cap = detectPushCapability();
    setCapability(cap);
    if (!cap.supported) {
      setEnabled(false);
      return;
    }
    const sub = await currentSubscription();
    setEnabled(cap.permission === 'granted' && !!sub);
  }, []);

  useEffect(() => {
    void refresh();
    const onVis = () => {
      if (document.visibilityState === 'visible') void refresh();
    };
    document.addEventListener('visibilitychange', onVis);
    return () => document.removeEventListener('visibilitychange', onVis);
  }, [refresh]);

  const enable = useCallback(() => {
    void (async () => {
      const cap = detectPushCapability();
      if (!cap.available) {
        toast.error(cap.iosNeedsInstall ? 'Add LoreWeave to your Home Screen to get nudges.' : 'Notifications aren’t available here.');
        return;
      }
      setBusy(true);
      try {
        // Ask only from a real user gesture (this handler) and only when not already granted.
        const perm = cap.permission === 'granted' ? 'granted' : await Notification.requestPermission();
        if (perm !== 'granted') {
          toast.message('Notifications are off. You can enable them in device settings.');
          await refresh();
          return;
        }
        const vapid = await pushApi.getVapidKey(accessToken);
        if (!vapid.configured || !vapid.public_key) {
          toast.error('Push isn’t configured on this server yet.');
          return;
        }
        const reg = await navigator.serviceWorker.ready;
        const sub =
          (await reg.pushManager.getSubscription()) ??
          (await reg.pushManager.subscribe({
            userVisibleOnly: true,
            // cast: the DOM lib's applicationServerKey wants BufferSource<ArrayBuffer>; our helper
            // returns a Uint8Array whose ambient buffer type is wider. Runtime value is correct.
            applicationServerKey: urlBase64ToUint8Array(vapid.public_key) as BufferSource,
          }));
        await pushApi.register(accessToken, sub.toJSON());
        setEnabled(true);
        toast.success('Notifications on.');
      } catch {
        toast.error('Couldn’t turn on notifications.');
      } finally {
        setBusy(false);
        await refresh();
      }
    })();
  }, [accessToken, refresh]);

  const disable = useCallback(() => {
    void (async () => {
      setBusy(true);
      try {
        const sub = await currentSubscription();
        if (sub) {
          await pushApi.unregister(accessToken, sub.endpoint).catch(() => {});
          await sub.unsubscribe().catch(() => {});
        }
        setEnabled(false);
        toast.success('Notifications off.');
      } finally {
        setBusy(false);
        await refresh();
      }
    })();
  }, [accessToken, refresh]);

  return { capability, enabled, busy, enable, disable };
}
