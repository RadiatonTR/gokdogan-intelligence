/**
 * AisUpstreamBanner — visible notice that AIS ship data is unavailable
 * because the upstream provider (AISStream) is offline.
 *
 * Renders nothing when AIS is healthy or when AIS isn't configured at all.
 * Mounted at the app shell level so users see it before they wonder why
 * the ocean looks empty.
 */
import { useEffect, useState } from 'react';
import { useAisUpstreamHealth } from '@/hooks/useAisUpstreamHealth';

export function AisUpstreamBanner() {
  const health = useAisUpstreamHealth();
  const [dismissed, setDismissed] = useState(false);
  const [graceElapsed, setGraceElapsed] = useState(false);

  useEffect(() => {
    if (!health?.aisEnabled || health.connected) {
      setGraceElapsed(false);
      return;
    }
    const timer = window.setTimeout(() => setGraceElapsed(true), 90_000);
    return () => window.clearTimeout(timer);
  }, [health?.aisEnabled, health?.connected]);

  if (!health || !health.aisEnabled || health.connected || dismissed || !graceElapsed) {
    return null;
  }

  // Format the staleness for the operator. ``null`` means we never received
  // anything since startup; otherwise show minutes if > 60s.
  let stalenessLabel = 'bu oturumda henüz veri alınmadı';
  if (health.lastMsgAgeSeconds != null) {
    const minutes = Math.floor(health.lastMsgAgeSeconds / 60);
    if (minutes >= 1) {
      stalenessLabel = `son güncelleme ${minutes} dk önce`;
    } else {
      stalenessLabel = `son güncelleme ${health.lastMsgAgeSeconds} sn önce`;
    }
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-auto fixed top-3 left-1/2 z-[100] -translate-x-1/2 max-w-[640px] rounded-md border border-amber-500/60 bg-amber-900/85 px-4 py-2 text-sm text-amber-50 shadow-lg backdrop-blur"
    >
      <div className="flex items-start gap-3">
        <span aria-hidden className="mt-0.5 text-amber-300">⚠</span>
        <div className="flex-1">
          <div className="font-semibold">AIS canlı gemi akışı bekleniyor</div>
          <div className="text-xs opacity-90">
            AISStream kaynağı şu anda veri göndermiyor ({stalenessLabel}). Diğer kullanılabilir deniz
            kaynakları ve önbellek çalışmaya devam eder. AISStream yeniden erişilebilir olduğunda
            canlı AIS verileri otomatik olarak birleşecektir.
          </div>
        </div>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          aria-label="Bildirimi kapat"
          className="text-amber-200 hover:text-white"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

export default AisUpstreamBanner;
