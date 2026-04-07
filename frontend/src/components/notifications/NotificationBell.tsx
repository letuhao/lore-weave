import { useState } from 'react';
import { Bell } from 'lucide-react';

// No notifications backend yet — show empty state until notification service is built

export function NotificationBell() {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="relative flex items-center gap-3 rounded-md px-2 py-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
      >
        <Bell className="h-4 w-4" />
        <span>Notifications</span>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute bottom-full left-0 z-50 mb-2 w-72 rounded-lg border bg-card shadow-xl">
            <div className="border-b px-4 py-3">
              <span className="text-sm font-semibold">Notifications</span>
            </div>
            <div className="flex flex-col items-center gap-2 py-8 text-muted-foreground">
              <Bell className="h-6 w-6 opacity-30" />
              <p className="text-xs">No notifications yet</p>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
