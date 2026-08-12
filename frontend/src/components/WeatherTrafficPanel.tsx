'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { CloudRain, CloudSun, RefreshCw, Route, Thermometer, Wind, Waves, Gauge } from 'lucide-react';

type Bounds = { south: number; west: number; north: number; east: number };
type WeatherPayload = {
  ok?: boolean;
  source?: string;
  fetched_at?: string;
  timezone?: string;
  current?: Record<string, number | string | null>;
  next_12h?: Array<Record<string, number | string | null>>;
  temperature_change?: Record<string, { min?: number | null; max?: number | null; mean?: number | null; change?: number | null }>;
  risk_flags?: Array<{kind?: string; level?: string; label?: string}>;
  daily?: Record<string, unknown[]>;
};
type AirPayload = { ok?: boolean; source?: string; current?: Record<string, number | string | null> };
type MarinePayload = { ok?: boolean; source?: string; current?: Record<string, number | string | null> };
type TrafficPayload = { ok?: boolean; configured?: boolean; provider?: string; detail?: string };
type IncidentPayload = { ok?: boolean; configured?: boolean; incidents?: Array<Record<string, unknown>>; detail?: string };

function n(value: unknown, digits = 0) {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : '—';
}

function trendLabel(change: number | null | undefined) {
  if (change == null || !Number.isFinite(Number(change))) return '—';
  const value = Number(change);
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}°C`;
}

export default function WeatherTrafficPanel({
  viewBoundsRef,
  onOpenSettings,
}: {
  viewBoundsRef: React.RefObject<Bounds | null>;
  onOpenSettings?: () => void;
}) {
  const [open, setOpen] = useState(true);
  const [loading, setLoading] = useState(false);
  const [weather, setWeather] = useState<WeatherPayload | null>(null);
  const [traffic, setTraffic] = useState<TrafficPayload | null>(null);
  const [incidents, setIncidents] = useState<IncidentPayload | null>(null);
  const [air, setAir] = useState<AirPayload | null>(null);
  const [marine, setMarine] = useState<MarinePayload | null>(null);
  const [error, setError] = useState('');

  const currentBounds = useCallback((): Bounds => {
    return viewBoundsRef.current || { south: 38.5, west: 26.0, north: 42.2, east: 45.0 };
  }, [viewBoundsRef]);

  const refresh = useCallback(async () => {
    const bounds = currentBounds();
    const lat = (bounds.south + bounds.north) / 2;
    const lng = (bounds.west + bounds.east) / 2;
    setLoading(true);
    setError('');
    try {
      const [weatherRes, trafficRes, airRes, marineRes] = await Promise.all([
        fetch(`/api/weather/forecast?lat=${lat.toFixed(5)}&lng=${lng.toFixed(5)}`, { cache: 'no-store' }),
        fetch('/api/traffic/status', { cache: 'no-store' }),
        fetch(`/api/weather/air-quality?lat=${lat.toFixed(5)}&lng=${lng.toFixed(5)}`, { cache: 'no-store' }),
        fetch(`/api/weather/marine?lat=${lat.toFixed(5)}&lng=${lng.toFixed(5)}`, { cache: 'no-store' }),
      ]);
      const weatherData = await weatherRes.json().catch(() => ({}));
      const trafficData = await trafficRes.json().catch(() => ({}));
      const airData = await airRes.json().catch(() => ({}));
      const marineData = await marineRes.json().catch(() => ({}));
      if (!weatherRes.ok || weatherData?.ok === false) throw new Error('Hava durumu verisi alınamadı.');
      setWeather(weatherData);
      setTraffic(trafficData);
      setAir(airRes.ok && airData?.ok !== false ? airData : null);
      setMarine(marineRes.ok && marineData?.ok !== false ? marineData : null);

      const area = (bounds.north - bounds.south) * (bounds.east - bounds.west);
      if (trafficData?.configured && area > 0 && area <= 25) {
        const qs = new URLSearchParams({
          south: String(bounds.south), west: String(bounds.west), north: String(bounds.north), east: String(bounds.east),
        });
        const res = await fetch(`/api/traffic/incidents?${qs.toString()}`, { cache: 'no-store' });
        setIncidents(await res.json().catch(() => ({})));
      } else {
        setIncidents(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Hava ve trafik verileri yenilenemedi.');
    } finally {
      setLoading(false);
    }
  }, [currentBounds]);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5 * 60 * 1000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const current = weather?.current || {};
  const nextHours = useMemo(() => (weather?.next_12h || []).slice(0, 6), [weather]);
  const history = weather?.temperature_change || {};
  const daily = weather?.daily || {};
  const dailyTimes = Array.isArray(daily.time) ? daily.time.slice(-16) : [];
  const airCurrent = air?.current || {};
  const marineCurrent = marine?.current || {};

  return (
    <section className="border border-cyan-900/60 bg-[#05090d]/94 font-mono text-cyan-200 flex-shrink-0">
      <button className="w-full px-3 py-2 flex items-center justify-between hover:bg-cyan-950/30" onClick={() => setOpen((v) => !v)}>
        <span className="flex items-center gap-2 text-[10px] tracking-[0.16em] font-bold"><CloudSun size={12} /> HAVA & KARA TRAFİĞİ</span>
        <span className="flex items-center gap-2 text-[8px] text-emerald-400">GERÇEK VERİ <span>{open ? '−' : '+'}</span></span>
      </button>
      {open && (
        <div className="border-t border-cyan-900/40 p-3 space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-[8px] text-cyan-600">Open-Meteo • RainViewer • TomTom Traffic</div>
            <button onClick={() => void refresh()} disabled={loading} className="text-cyan-400 hover:text-white" title="Verileri yenile">
              <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>

          {error && <div className="text-[9px] border border-red-800/50 bg-red-950/25 p-2 text-red-300">{error}</div>}

          <div className="grid grid-cols-3 gap-1">
            <div className="border border-cyan-900/40 p-2"><Thermometer size={10} /><div className="text-[15px] text-white mt-1">{n(current.temperature_2m, 1)}°C</div><div className="text-[7px] text-cyan-600">HİS {n(current.apparent_temperature, 1)}°C</div></div>
            <div className="border border-cyan-900/40 p-2"><CloudRain size={10} /><div className="text-[15px] text-white mt-1">%{n(current.cloud_cover)}</div><div className="text-[7px] text-cyan-600">BULUT • YAĞIŞ {n(current.precipitation, 1)} mm</div></div>
            <div className="border border-cyan-900/40 p-2"><Wind size={10} /><div className="text-[15px] text-white mt-1">{n(current.wind_speed_10m)}</div><div className="text-[7px] text-cyan-600">km/sa • HAMLE {n(current.wind_gusts_10m)}</div></div>
          </div>

          <div>
            <div className="text-[8px] tracking-wider text-cyan-500 mb-1">YAKLAŞAN 6 SAAT</div>
            <div className="grid grid-cols-6 gap-[2px]">
              {nextHours.map((hour, idx) => (
                <div key={`${String(hour.time)}-${idx}`} className="border border-cyan-950/70 bg-black/20 p-1 text-center">
                  <div className="text-[7px] text-cyan-600">{String(hour.time || '').slice(11, 16)}</div>
                  <div className="text-[9px] text-white">{n(hour.temperature)}°</div>
                  <div className="text-[7px] text-sky-300">☁ %{n(hour.cloud_cover)}</div>
                  <div className="text-[6px] text-sky-700">A/O/Y {n(hour.cloud_cover_low)}/{n(hour.cloud_cover_mid)}/{n(hour.cloud_cover_high)}</div>
                  <div className="text-[7px] text-cyan-400">☂ %{n(hour.precip_probability)}</div>
                </div>
              ))}
            </div>
          </div>

          {(weather?.risk_flags || []).length > 0 && (
            <div className="border border-red-900/50 bg-red-950/15 p-2">
              <div className="text-[8px] text-red-300 tracking-wider">HAVA RİSKLERİ</div>
              <div className="flex flex-wrap gap-1 mt-1">{(weather?.risk_flags || []).map((flag, idx) => <span key={`${flag.kind}-${idx}`} className="border border-red-800/40 px-1.5 py-0.5 text-[7px] text-red-200">{flag.label}</span>)}</div>
            </div>
          )}

          <div>
            <div className="text-[8px] tracking-wider text-cyan-500 mb-1">16 GÜNLÜK HAVA TABLOSU</div>
            <div className="grid grid-cols-4 gap-[2px] max-h-[120px] overflow-y-auto styled-scrollbar">
              {dailyTimes.map((stamp, idx) => {
                const date = String(stamp);
                const allTimes = Array.isArray(daily.time) ? daily.time : [];
                const sourceIndex = allTimes.indexOf(stamp);
                const max = Array.isArray(daily.temperature_2m_max) ? daily.temperature_2m_max[sourceIndex] : null;
                const min = Array.isArray(daily.temperature_2m_min) ? daily.temperature_2m_min[sourceIndex] : null;
                const rain = Array.isArray(daily.precipitation_sum) ? daily.precipitation_sum[sourceIndex] : null;
                return <div key={`${date}-${idx}`} className="border border-cyan-950/60 p-1"><div className="text-[7px] text-cyan-600">{date.slice(5)}</div><div className="text-[8px] text-white">{n(min)}° / {n(max)}°</div><div className="text-[7px] text-sky-400">☂ {n(rain,1)} mm</div></div>;
              })}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-1">
            <div className="border border-cyan-900/40 p-2"><div className="flex items-center gap-1 text-[8px] text-cyan-400"><Gauge size={10}/> HAVA KALİTESİ</div><div className="text-[11px] text-white mt-1">AQI {n(airCurrent.european_aqi)}</div><div className="text-[7px] text-cyan-700">PM2.5 {n(airCurrent.pm2_5,1)} µg/m³ • PM10 {n(airCurrent.pm10,1)}</div></div>
            <div className="border border-cyan-900/40 p-2"><div className="flex items-center gap-1 text-[8px] text-cyan-400"><Waves size={10}/> DENİZ DURUMU</div><div className="text-[11px] text-white mt-1">Dalga {n(marineCurrent.wave_height,1)} m</div><div className="text-[7px] text-cyan-700">SST {n(marineCurrent.sea_surface_temperature,1)}°C • akıntı {n(marineCurrent.ocean_current_velocity,2)}</div></div>
          </div>

          <div>
            <div className="text-[8px] tracking-wider text-cyan-500 mb-1">SICAKLIK DEĞİŞİMİ</div>
            <div className="grid grid-cols-3 gap-1 text-[8px]">
              {([['day', 'GÜN'], ['week', 'HAFTA'], ['month', 'AY']] as const).map(([key, label]) => (
                <div key={key} className="border border-cyan-900/40 p-2">
                  <div className="text-cyan-600">{label}</div>
                  <div className="text-white text-[11px] mt-1">{trendLabel(history[key]?.change)}</div>
                  <div className="text-[7px] text-cyan-700">{n(history[key]?.min, 1)} / {n(history[key]?.max, 1)}°C</div>
                </div>
              ))}
            </div>
          </div>

          <div className="border border-amber-900/40 bg-amber-950/10 p-2 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div>
                <div className="flex items-center gap-1 text-[9px] text-amber-300"><Route size={10} /> KARA TRAFİĞİ & OLAYLAR</div>
                <div className="text-[7px] text-amber-500/80 mt-1">
                  {traffic?.configured ? `TomTom canlı • görünümde olay: ${incidents?.incidents?.length ?? '—'}` : 'TomTom API anahtarı gerekli • trafik akışı ve olay katmanı anahtarsız boş kalır'}
                </div>
              </div>
              {!traffic?.configured && onOpenSettings && <button onClick={onOpenSettings} className="border border-amber-700/50 px-2 py-1 text-[7px] text-amber-300 hover:bg-amber-950/40">ANAHTAR EKLE</button>}
            </div>
            {(incidents?.incidents || []).slice(0, 4).map((incident, idx) => {
              const props = (incident.properties || {}) as Record<string, unknown>;
              const events = Array.isArray(props.events) ? props.events as Array<Record<string, unknown>> : [];
              const desc = String(events[0]?.description || props.from || 'Trafik olayı');
              const delay = Number(props.delayInSeconds);
              return <div key={`${String(props.id || idx)}`} className="border-t border-amber-950/50 pt-1 text-[7px]"><span className="text-amber-200">{desc}</span><span className="text-amber-700">{Number.isFinite(delay) && delay > 0 ? ` • gecikme ${Math.round(delay / 60)} dk` : ''}{props.roadNumbers ? ` • ${String(props.roadNumbers)}` : ''}</span></div>;
            })}
            {incidents?.detail === 'zoom_in_for_incidents' ? <div className="text-[7px] text-amber-600">Kaza/olay ayrıntısı için haritayı yakınlaştırın.</div> : null}
          </div>
        </div>
      )}
    </section>
  );
}
