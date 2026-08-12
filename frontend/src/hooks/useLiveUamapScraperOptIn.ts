'use client';

import { useCallback, useEffect, useState } from 'react';
import { API_BASE } from '@/lib/api';

export type LiveUamapScraperStatus = {
  platform_requires_opt_in: boolean;
  ui_opted_in: boolean;
  scraper_enabled: boolean;
  env_override: 'on' | 'off' | null;
};

export function useLiveUamapScraperOptIn(enabled = true) {
  const [status, setStatus] = useState<LiveUamapScraperStatus | null>(null);

  const refreshStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/liveuamap/scraper-status`);
      if (!res.ok) return;
      const body = (await res.json()) as LiveUamapScraperStatus;
      setStatus(body);
    } catch {
      // Backend may still be starting.
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    void refreshStatus();
  }, [enabled, refreshStatus]);

  const needsConsentBeforeEnable = useCallback(
    (layerId: string, turningOn: boolean) =>
      layerId === 'global_incidents' &&
      turningOn &&
      Boolean(status?.platform_requires_opt_in) &&
      !status?.ui_opted_in,
    [status],
  );

  const confirmOptIn = useCallback(async () => {
    const res = await fetch(`${API_BASE}/api/liveuamap/scraper-opt-in`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ opted_in: true }),
    });
    if (!res.ok) {
      throw new Error(`LiveUAMap opt-in failed (${res.status})`);
    }
    const body = (await res.json()) as LiveUamapScraperStatus;
    setStatus(body);
    return body;
  }, []);

  return {
    status,
    refreshStatus,
    needsConsentBeforeEnable,
    confirmOptIn,
  };
}
