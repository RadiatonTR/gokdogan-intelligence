'use client';

import { useEffect } from 'react';

type AlertRow = {
  id: string;
  title: string;
  severity: string;
  status: string;
  created_at?: string;
};

const ENABLE_KEY = 'sb_desktop_notifications';
const CURSOR_KEY = 'sb_last_intelligence_notification_alert';
const IMPORTANT = new Set(['critical', 'flash', 'priority']);

async function emitNotification(alert: AlertRow): Promise<void> {
  const title = `Gokdogan • ${String(alert.severity || 'alert').toUpperCase()}`;
  const body = String(alert.title || 'New intelligence alert');
  const nativeNotify = window.__SHADOWBROKER_DESKTOP__?.notify;
  if (nativeNotify) {
    await nativeNotify(title, body);
    return;
  }
  if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
    new Notification(title, { body });
  }
}

/**
 * Always-mounted local alert watcher for the dashboard.
 *
 * It never enables notifications by itself. The user must opt in from the
 * Intelligence Center. On first observation it establishes a cursor without
 * replaying historical alerts; subsequent polls notify only newly-created,
 * high-priority local alerts. The cursor is persisted so an app restart does
 * not replay the same notification storm.
 */
export function useIntelligenceAlertNotifications(pollMs = 12_000): void {
  useEffect(() => {
    let stopped = false;
    let running = false;

    const poll = async () => {
      if (stopped || running) return;
      let enabled = false;
      try { enabled = localStorage.getItem(ENABLE_KEY) === 'true'; } catch { return; }
      if (!enabled) return;
      running = true;
      try {
        const response = await fetch('/api/intelligence/alerts?limit=50', {
          method: 'GET',
          cache: 'no-store',
          credentials: 'same-origin',
        });
        if (!response.ok) return;
        const payload = await response.json() as { alerts?: AlertRow[] };
        const rows = (payload.alerts || [])
          .filter((row) => row && row.id && row.status === 'new' && IMPORTANT.has(String(row.severity || '').toLowerCase()))
          .sort((a, b) => String(a.created_at || '').localeCompare(String(b.created_at || '')));
        if (!rows.length) return;

        let cursor = '';
        try { cursor = localStorage.getItem(CURSOR_KEY) || ''; } catch {}
        if (!cursor) {
          // Opt-in should mean "new from now on", not replay every historical
          // unresolved alert in the local database.
          try { localStorage.setItem(CURSOR_KEY, rows[rows.length - 1].id); } catch {}
          return;
        }
        const cursorIndex = rows.findIndex((row) => row.id === cursor);
        const fresh = cursorIndex >= 0 ? rows.slice(cursorIndex + 1) : rows.slice(-1);
        for (const alert of fresh.slice(-3)) {
          if (stopped) break;
          try { await emitNotification(alert); } catch { /* notification failure must not affect dashboard */ }
          try { localStorage.setItem(CURSOR_KEY, alert.id); } catch {}
        }
      } catch {
        // Local backend can be starting/recovering; the next poll retries.
      } finally {
        running = false;
      }
    };

    const initial = window.setTimeout(() => { void poll(); }, 2_000);
    const timer = window.setInterval(() => { void poll(); }, Math.max(5_000, pollMs));
    return () => {
      stopped = true;
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [pollMs]);
}
