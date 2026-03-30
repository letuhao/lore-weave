import { useState } from 'react';
import { Bell, X, Check, MessageCircle, Languages, AlertTriangle, Heart, Star, BookOpen } from 'lucide-react';
import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';

type NotifType = 'translation' | 'comment' | 'review' | 'follow' | 'error' | 'milestone' | 'chapter';

type Notification = {
  id: string;
  type: NotifType;
  title: string;
  meta?: string;
  time: string;
  read: boolean;
};

// Mock data — real API in P2-09b
const MOCK: Notification[] = [
  { id: '1', type: 'translation', title: 'Translation complete — 5 chapters translated to English', meta: 'Claude Sonnet 4.6 · $0.12', time: '2m ago', read: false },
  { id: '2', type: 'comment', title: 'SakuraPen commented on Ch.3', meta: 'The Demon Lord\'s Duty', time: '15m ago', read: false },
  { id: '3', type: 'error', title: 'Translation failed — Ch.12 timeout', meta: 'GPT-4o · no tokens charged', time: '1h ago', read: true },
  { id: '4', type: 'follow', title: 'JadePeak started following you', meta: '42 followers', time: '3h ago', read: true },
];

const ICONS: Record<NotifType, { icon: React.ElementType; color: string }> = {
  translation: { icon: Check, color: 'bg-success/10 text-success' },
  comment:     { icon: MessageCircle, color: 'bg-info/10 text-info' },
  review:      { icon: Star, color: 'bg-primary/10 text-primary' },
  follow:      { icon: Heart, color: 'bg-[#e85d75]/10 text-[#e85d75]' },
  error:       { icon: AlertTriangle, color: 'bg-destructive/10 text-destructive' },
  milestone:   { icon: Star, color: 'bg-primary/10 text-primary' },
  chapter:     { icon: BookOpen, color: 'bg-accent/10 text-accent' },
};

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [notifications] = useState<Notification[]>(MOCK);
  const unread = notifications.filter((n) => !n.read).length;

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="relative flex items-center gap-3 rounded-md px-2 py-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
      >
        <Bell className="h-4 w-4" />
        <span>Notifications</span>
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-destructive px-1 text-[9px] font-bold text-white">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute bottom-full left-0 z-50 mb-2 w-80 rounded-lg border bg-card shadow-xl">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <span className="text-sm font-semibold">Notifications</span>
              <button className="text-xs text-muted-foreground hover:text-foreground">Mark all read</button>
            </div>
            <div className="max-h-80 overflow-y-auto">
              {notifications.map((n) => {
                const cfg = ICONS[n.type];
                const Icon = cfg.icon;
                return (
                  <div key={n.id} className={cn('flex gap-3 border-b px-4 py-3 text-xs', !n.read && 'bg-primary/[0.02]')}>
                    <div className={cn('flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg', cfg.color)}>
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="leading-relaxed">{n.title}</p>
                      {n.meta && <p className="mt-0.5 text-muted-foreground">{n.meta}</p>}
                    </div>
                    <span className="flex-shrink-0 text-muted-foreground">{n.time}</span>
                    {!n.read && <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-primary" />}
                  </div>
                );
              })}
            </div>
            <Link to="/notifications" onClick={() => setOpen(false)} className="block border-t px-4 py-2.5 text-center text-xs text-primary hover:bg-secondary">
              View all notifications
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
