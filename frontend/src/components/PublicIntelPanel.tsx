'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Camera,
  Globe2,
  MapPinned,
  Plane,
  RefreshCw,
  ShieldCheck,
  Ship,
  Siren,
  Waypoints,
} from 'lucide-react';

type Tab = 'news' | 'localNews' | 'diplomacy' | 'borders' | 'cameras' | 'movement' | 'disasters' | 'conflicts' | 'health';
type Json = Record<string, unknown>;

type HealthRow = {
  id?: string;
  name?: string;
  category?: string;
  turkish_category?: string;
  state?: string;
  turkish_state?: string;
  mode?: string;
  turkish_mode?: string;
  note?: string;
  records?: number;
  age_seconds?: number | null;
  stale_after_seconds?: number | null;
  configured?: boolean;
  refreshable?: boolean;
  last_probe?: { ok?: boolean; status?: number | null; latency_ms?: number | null; detail?: string | null; tested_at?: string } | null;
};

type CapabilityRow = { id?: string; name?: string; state?: string; detail?: string };

function ageLabel(value: unknown) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds)) return '—';
  if (seconds < 60) return `${Math.round(seconds)} sn`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} dk`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)} sa`;
  return `${(seconds / 86400).toFixed(1)} gün`;
}

function short(value: unknown, max = 120) {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim();
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function present(value: unknown) {
  return value !== undefined && value !== null && String(value).trim() !== '';
}

function coordinate(item: Json): [number, number] | null {
  const lat = Number(item.lat);
  const lng = Number(item.lng ?? item.lon);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  return [lat, lng];
}

export default function PublicIntelPanel({ onLocate }: { onLocate?: (lat: number, lng: number) => void }) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>('news');
  const [data, setData] = useState<Json>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [testing, setTesting] = useState('');
  const [testingAll, setTestingAll] = useState(false);
  const [testSummary, setTestSummary] = useState('');
  const [refreshingProvider, setRefreshingProvider] = useState('');
  const [testResults, setTestResults] = useState<Record<string, string>>({});
  const [cameraPreview, setCameraPreview] = useState<Json | null>(null);
  const [movementDetail, setMovementDetail] = useState<Json | null>(null);
  const [movementDetailLoading, setMovementDetailLoading] = useState('');

  const endpoint = useMemo(() => {
    if (tab === 'news') return '/api/public-intel/breaking-news?scope=global&limit=24&turkish=true';
    if (tab === 'localNews') return '/api/public-intel/breaking-news?scope=local&limit=24&turkish=true';
    if (tab === 'diplomacy') return '/api/public-intel/diplomacy?limit=30';
    if (tab === 'borders') return '/api/public-intel/borders?limit=200';
    if (tab === 'cameras') return '/api/public-intel/public-cameras?limit=300';
    if (tab === 'movement') return '/api/public-intel/civilian-movement?limit=120';
    if (tab === 'disasters') return '/api/public-intel/disasters?limit=300';
    if (tab === 'conflicts') return '/api/public-intel/conflict-regions?limit=120';
    return '/api/public-intel/provider-health';
  }, [tab]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(endpoint, { cache: 'no-store' });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok || payload?.ok === false) throw new Error('Canlı operasyon verisi alınamadı.');
      setData(payload);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Canlı operasyon verisi alınamadı.');
    } finally {
      setLoading(false);
    }
  }, [endpoint]);

  useEffect(() => {
    if (!open) return;
    void refresh();
    const fastTabs: Tab[] = ['news', 'localNews', 'movement', 'cameras'];
    const timer = window.setInterval(() => void refresh(), fastTabs.includes(tab) ? 60_000 : 120_000);
    return () => window.clearInterval(timer);
  }, [open, refresh, tab]);

  const testProvider = useCallback(async (id: string) => {
    setTesting(id);
    try {
      const res = await fetch(`/api/public-intel/provider-test/${encodeURIComponent(id)}`, { method: 'POST', cache: 'no-store' });
      const payload = await res.json().catch(() => ({}));
      const label = payload?.ok ? `TEST BAŞARILI${payload?.latency_ms ? ` • ${payload.latency_ms} ms` : ''}` : `TEST BAŞARISIZ • ${payload?.detail || payload?.status || 'dış kaynak'}`;
      setTestResults((prev) => ({ ...prev, [id]: label }));
    } catch {
      setTestResults((prev) => ({ ...prev, [id]: 'TEST BAŞARISIZ • bağlantı' }));
    } finally {
      setTesting('');
    }
  }, []);

  const testAllProviders = useCallback(async () => {
    setTestingAll(true);
    setTestSummary('');
    try {
      const res = await fetch('/api/public-intel/provider-test-all', { method: 'POST', cache: 'no-store' });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok || payload?.ok === false) throw new Error('Toplu kaynak testi başarısız.');
      const mapped: Record<string, string> = {};
      Object.entries((payload?.results || {}) as Record<string, Record<string, unknown>>).forEach(([id, row]) => {
        mapped[id] = row?.ok
          ? `TEST BAŞARILI${row?.latency_ms ? ` • ${String(row.latency_ms)} ms` : ''}`
          : `TEST BAŞARISIZ • ${String(row?.detail || row?.status || 'dış servis')}`;
      });
      setTestResults((prev) => ({ ...prev, ...mapped }));
      setTestSummary(`${Number(payload?.passed || 0)}/${Number(payload?.tested || 0)} kaynak erişilebilir`);
      await refresh();
    } catch (e) {
      setTestSummary(e instanceof Error ? e.message : 'Toplu kaynak testi başarısız.');
    } finally {
      setTestingAll(false);
    }
  }, [refresh]);

  const refreshProvider = useCallback(async (id: string) => {
    setRefreshingProvider(id);
    try {
      const res = await fetch(`/api/public-intel/provider-refresh/${encodeURIComponent(id)}`, { method: 'POST', cache: 'no-store' });
      const payload = await res.json().catch(() => ({}));
      setTestResults((prev) => ({ ...prev, [id]: payload?.ok === false ? `YENİLEME BAŞARISIZ • ${payload?.detail || 'kaynak'}` : 'YENİLEME TETİKLENDİ' }));
      window.setTimeout(() => void refresh(), 1200);
    } catch {
      setTestResults((prev) => ({ ...prev, [id]: 'YENİLEME BAŞARISIZ • bağlantı' }));
    } finally {
      setRefreshingProvider('');
    }
  }, [refresh]);

  const loadMovementDetail = useCallback(async (kind: 'aircraft' | 'vessel', identifier: string) => {
    if (!identifier) return;
    setMovementDetailLoading(`${kind}:${identifier}`);
    try {
      const path = kind === 'aircraft' ? 'civilian-aircraft' : 'civilian-vessel';
      const res = await fetch(`/api/public-intel/${path}/${encodeURIComponent(identifier)}`, { cache: 'no-store' });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok || payload?.ok === false) throw new Error(String(payload?.detail || 'Araç ayrıntısı alınamadı.'));
      setMovementDetail(payload);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Araç ayrıntısı alınamadı.');
    } finally {
      setMovementDetailLoading('');
    }
  }, []);

  const tabs: Array<[Tab, string]> = [
    ['news', 'KÜRESEL HABER / SON DAKİKA'],
    ['localNews', 'YEREL HABER / SON DAKİKA'],
    ['diplomacy', 'DİPLOMASİ'],
    ['borders', 'SINIRLAR'],
    ['cameras', 'KAMERALAR'],
    ['movement', 'ARAÇLAR'],
    ['disasters', 'AFETLER'],
    ['conflicts', 'ÇATIŞMALAR'],
    ['health', 'SAĞLIK / KAYNAK SAĞLIĞI'],
  ];

  const newsRows = (data.items as Json[] | undefined) || [];

  return (
    <section className="border border-cyan-900/60 bg-[#05090d]/94 font-mono text-cyan-200 flex-shrink-0">
      <button className="w-full px-3 py-2 flex items-center justify-between hover:bg-cyan-950/30" onClick={() => setOpen((v) => !v)}>
        <span className="flex items-center gap-2 text-[10px] tracking-[0.16em] font-bold"><Globe2 size={12} /> GÖKDOĞAN CANLI OPERASYON MERKEZİ</span>
        <span className="flex items-center gap-2 text-[8px] text-emerald-400">KAMU / YETKİLİ KAYNAK <span>{open ? '−' : '+'}</span></span>
      </button>
      {open && (
        <div className="border-t border-cyan-900/40">
          <div className="grid grid-cols-3 border-b border-cyan-900/40">
            {tabs.map(([key, label]) => (
              <button key={key} onClick={() => { setTab(key); setCameraPreview(null); setMovementDetail(null); }} className={`py-2 px-1 text-[7px] tracking-wider ${tab === key ? 'bg-cyan-950/45 text-white' : 'text-cyan-600 hover:text-cyan-300'}`}>{label}</button>
            ))}
          </div>
          <div className="p-2 max-h-[390px] overflow-y-auto styled-scrollbar space-y-2">
            <div className="flex items-center justify-between text-[7px] text-cyan-700">
              <span>Gerçek kaynak • sahte/demo veri yok • canlı/önbellek tazeliği kaynak durumuyla birlikte izlenir</span>
              <button onClick={() => void refresh()} disabled={loading} className="text-cyan-400 hover:text-white" title="Yenile"><RefreshCw size={10} className={loading ? 'animate-spin' : ''} /></button>
            </div>
            {error && <div className="border border-red-900/50 bg-red-950/20 text-red-300 p-2 text-[8px]">{error}</div>}

            {(tab === 'news' || tab === 'localNews' || tab === 'diplomacy') && newsRows.map((item, idx) => (
              <a key={`${String(item.url)}-${idx}`} href={String(item.url || '#')} target="_blank" rel="noreferrer" className="block border border-cyan-950/70 bg-black/20 p-2 hover:border-cyan-700/60">
                <div className="text-[8px] text-cyan-600">{String(item.provider || 'Açık kaynak')} • {String(item.published_at || 'zaman bilinmiyor')}{item.source_lang_label ? ` • kaynak dili: ${String(item.source_lang_label)}` : ''}</div>
                <div className="text-[9px] text-white mt-1 leading-relaxed">{short(item.title, 180)}</div>
                {item.summary ? <div className="text-[7px] text-cyan-700 mt-1">{short(item.summary, 220)}</div> : null}
                {item.url ? <div className="text-[7px] text-emerald-500 mt-1">SİSTEM TARAYICISINDA KAYNAĞI AÇ ↗</div> : null}
              </a>
            ))}

            {tab === 'borders' && ((data.crossings as Json[] | undefined) || []).map((item, idx) => {
              const point = coordinate(item);
              return <div key={`${String(item.id)}-${idx}`} className="border border-amber-950/60 bg-amber-950/10 p-2">
                <div className="flex items-center gap-1 text-[8px] text-amber-300"><Waypoints size={10} /> {short(item.name, 110)}</div>
                <div className="text-[7px] text-amber-600 mt-1">{String(item.country_pair || '')} • {String(item.provider || '')}</div>
                <div className="text-[8px] text-white mt-1">{item.wait_minutes == null ? short(item.status_text, 190) : `Güncel bekleme: ${String(item.wait_minutes)} dk`}</div>
                {present(item.public_camera_count) ? <div className="text-[7px] text-cyan-600 mt-1">Kamu kamera kaydı: {String(item.public_camera_count)}</div> : null}
                <div className="flex gap-2 mt-1">
                  {point && onLocate ? <button onClick={() => onLocate(point[0], point[1])} className="text-[7px] text-amber-300 hover:text-white">HARİTADA GÖSTER</button> : null}
                  {item.url ? <a href={String(item.url)} target="_blank" rel="noreferrer" className="text-[7px] text-cyan-400 hover:text-white">RESMÎ KAYNAĞI AÇ ↗</a> : null}
                </div>
              </div>;
            })}

            {tab === 'cameras' && (
              <div className="space-y-2">
                {cameraPreview && String(cameraPreview.media_url || '').startsWith('http') && String(cameraPreview.media_type || 'image').toLowerCase() === 'image' ? (
                  <div className="border border-cyan-800/60 bg-black/40 p-2">
                    <div className="flex items-center justify-between text-[8px] text-white mb-2"><span>{short(cameraPreview.name, 120)}</span><button className="text-cyan-500" onClick={() => setCameraPreview(null)}>ÖNİZLEMEYİ KAPAT</button></div>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={String(cameraPreview.media_url)} alt={String(cameraPreview.name || 'Kamu kamera görüntüsü')} className="w-full max-h-52 object-contain bg-black" referrerPolicy="no-referrer" />
                  </div>
                ) : null}
                {((data.items as Json[] | undefined) || []).map((item, idx) => {
                  const point = coordinate(item);
                  const mediaType = String(item.media_type || 'image').toLowerCase();
                  return <div key={`${String(item.id)}-${idx}`} className="border border-cyan-950/70 bg-black/20 p-2">
                    <div className="flex items-center gap-1 text-[8px] text-white"><Camera size={10} /> {short(item.name, 120)}</div>
                    <div className="text-[7px] text-cyan-600 mt-1">{String(item.source_agency || 'Kamu kamera kaynağı')} • {mediaType.toUpperCase()} • KAMU ERİŞİMİ</div>
                    <div className="flex flex-wrap gap-2 mt-2">
                      {point && onLocate ? <button onClick={() => onLocate(point[0], point[1])} className="text-[7px] text-amber-300 hover:text-white">HARİTADA GÖSTER</button> : null}
                      {item.media_url && mediaType === 'image' ? <button onClick={() => setCameraPreview(item)} className="text-[7px] text-emerald-400 hover:text-white">SİSTEM İÇİNDE ÖNİZLE</button> : null}
                      {item.media_url ? <a href={String(item.media_url)} target="_blank" rel="noreferrer" className="text-[7px] text-cyan-400 hover:text-white">KAYNAĞI/YAYINI AÇ ↗</a> : null}
                    </div>
                  </div>;
                })}
              </div>
            )}

            {tab === 'movement' && (
              <div className="space-y-3">
                {movementDetail ? (
                  <div className="border border-emerald-900/60 bg-emerald-950/10 p-2">
                    <div className="flex items-center justify-between">
                      <div className="text-[8px] text-emerald-300">AYRINTILI ROTA KAYDI</div>
                      <button className="text-[7px] text-cyan-500 hover:text-white" onClick={() => setMovementDetail(null)}>KAPAT</button>
                    </div>
                    {movementDetail.aircraft ? (
                      <div className="mt-1 text-[8px] text-slate-300">
                        {short((movementDetail.aircraft as Json).callsign || (movementDetail.aircraft as Json).registration || 'Hava aracı', 90)} • {(movementDetail.aircraft as Json).origin ? String((movementDetail.aircraft as Json).origin) : 'kalkış bilinmiyor'} → {(movementDetail.aircraft as Json).destination ? String((movementDetail.aircraft as Json).destination) : 'varış bilinmiyor'}
                      </div>
                    ) : null}
                    {movementDetail.vessel ? (
                      <div className="mt-1 text-[8px] text-slate-300">
                        {short((movementDetail.vessel as Json).name || (movementDetail.vessel as Json).mmsi || 'Deniz aracı', 90)} • {(movementDetail.vessel as Json).origin ? String((movementDetail.vessel as Json).origin) : 'kalkış bilinmiyor'} → {(movementDetail.vessel as Json).destination ? String((movementDetail.vessel as Json).destination) : 'varış bilinmiyor'}
                      </div>
                    ) : null}
                    <div className="mt-1 text-[7px] text-slate-500">
                      Gözlenen rota noktası: {String((movementDetail.trail as Json | undefined)?.point_count ?? 0)} • gözlenen süre: {ageLabel((movementDetail.trail as Json | undefined)?.observed_duration_seconds)}
                    </div>
                    <div className="text-[7px] text-slate-600">İlk gözlem: {String((movementDetail.trail as Json | undefined)?.first_observed_at || '—')} • son gözlem: {String((movementDetail.trail as Json | undefined)?.last_observed_at || '—')}</div>
                    {Array.isArray((movementDetail.trail as Json | undefined)?.points) && ((movementDetail.trail as Json).points as unknown[]).length > 0 ? (
                      <div className="mt-2 max-h-24 overflow-y-auto styled-scrollbar text-[7px] text-cyan-700">
                        {(((movementDetail.trail as Json).points as unknown[]).slice(-20) as unknown[]).map((raw, idx) => {
                          const point = raw as unknown[];
                          return <div key={idx}>#{idx + 1} • {Number(point[0]).toFixed(4)}, {Number(point[1]).toFixed(4)} • {point[2] == null ? '—' : String(point[2])}</div>;
                        })}
                      </div>
                    ) : <div className="mt-2 text-[7px] text-slate-600">Bu çalışma oturumunda henüz yeterli rota noktası birikmedi.</div>}
                  </div>
                ) : null}
                <div className="border border-cyan-900/50 p-2">
                  <div className="flex items-center gap-1 text-[8px] text-white"><Plane size={10} /> SİVİL / TİCARİ HAVA ARAÇLARI • {Number((data.counts as Json | undefined)?.aircraft || 0).toLocaleString()}</div>
                  <div className="mt-2 space-y-1">
                    {((data.aircraft as Json[] | undefined) || []).slice(0, 60).map((item, idx) => {
                      const point = coordinate(item);
                      return <div key={`${String(item.id)}-${idx}`} className="border border-slate-900/80 p-2 bg-black/20">
                        <div className="text-[8px] text-cyan-200">{short(item.callsign || item.registration || item.id || 'Hava aracı', 80)} {item.airline ? `• ${short(item.airline, 70)}` : ''}</div>
                        <div className="text-[7px] text-slate-500 mt-1">{short(item.model, 45)} • kalkış {String(item.origin || 'bilinmiyor')} → varış {String(item.destination || 'bilinmiyor')}</div>
                        <div className="text-[7px] text-slate-600">irtifa {String(item.altitude ?? '—')} • hız {String(item.speed ?? '—')} • yön {String(item.heading ?? '—')}</div>
                        <div className="flex gap-2 mt-1">
                          {point && onLocate ? <button onClick={() => onLocate(point[0], point[1])} className="text-[7px] text-amber-300">HARİTADA GÖSTER</button> : null}
                          <button onClick={() => void loadMovementDetail('aircraft', String(item.id || item.callsign || item.registration || ''))} disabled={movementDetailLoading === `aircraft:${String(item.id || item.callsign || item.registration || '')}`} className="text-[7px] text-emerald-400 hover:text-white">{movementDetailLoading === `aircraft:${String(item.id || item.callsign || item.registration || '')}` ? 'ROTA YÜKLENİYOR…' : 'ROTA KAYDI / DETAY'}</button>
                        </div>
                      </div>;
                    })}
                  </div>
                </div>
                <div className="border border-cyan-900/50 p-2">
                  <div className="flex items-center gap-1 text-[8px] text-white"><Ship size={10} /> SİVİL / TİCARİ DENİZ ARAÇLARI • {Number((data.counts as Json | undefined)?.vessels || 0).toLocaleString()}</div>
                  <div className="mt-2 space-y-1">
                    {((data.vessels as Json[] | undefined) || []).slice(0, 60).map((item, idx) => {
                      const point = coordinate(item);
                      return <div key={`${String(item.id)}-${idx}`} className="border border-slate-900/80 p-2 bg-black/20">
                        <div className="text-[8px] text-cyan-200">{short(item.name || item.id || 'Deniz aracı', 90)} • {short(item.vessel_type, 55)}</div>
                        <div className="text-[7px] text-slate-500 mt-1">MMSI {String(item.mmsi || '—')} • IMO {String(item.imo || '—')} • varış {String(item.destination || 'bilinmiyor')}</div>
                        <div className="text-[7px] text-slate-600">hız {String(item.speed ?? '—')} • rota/yön {String(item.course ?? '—')} • ETA {String(item.eta ?? '—')}</div>
                        <div className="flex gap-2 mt-1">
                          {point && onLocate ? <button onClick={() => onLocate(point[0], point[1])} className="text-[7px] text-amber-300">HARİTADA GÖSTER</button> : null}
                          <button onClick={() => void loadMovementDetail('vessel', String(item.mmsi || item.id || item.imo || ''))} disabled={movementDetailLoading === `vessel:${String(item.mmsi || item.id || item.imo || '')}`} className="text-[7px] text-emerald-400 hover:text-white">{movementDetailLoading === `vessel:${String(item.mmsi || item.id || item.imo || '')}` ? 'ROTA YÜKLENİYOR…' : 'ROTA KAYDI / DETAY'}</button>
                        </div>
                      </div>;
                    })}
                  </div>
                </div>
              </div>
            )}

            {tab === 'disasters' && ((data.global as Json[] | undefined) || []).map((item, idx) => {
              const point = coordinate(item);
              const content = <div className="border border-red-950/60 bg-red-950/10 p-2 hover:border-red-700/60">
                <div className="flex items-center gap-1 text-[8px] text-red-300"><Siren size={10} /> {short(item.title, 130)}</div>
                <div className="text-[7px] text-red-600 mt-1">{String(item.provider || '')} • {(item.categories as unknown[] | undefined)?.join(', ') || 'doğal olay'} • {String(item.alert_level || item.severity || '')}</div>
                <div className="flex gap-2 mt-1">
                  {point && onLocate ? <button onClick={(event) => { event.preventDefault(); onLocate(point[0], point[1]); }} className="text-[7px] text-amber-300">HARİTADA GÖSTER</button> : null}
                  {item.url ? <span className="text-[7px] text-cyan-400">RESMÎ/KAMU KAYNAĞINI AÇ ↗</span> : null}
                </div>
              </div>;
              return item.url ? <a key={`${String(item.id)}-${idx}`} href={String(item.url)} target="_blank" rel="noreferrer" className="block">{content}</a> : <div key={`${String(item.id)}-${idx}`}>{content}</div>;
            })}

            {tab === 'conflicts' && (
              <div className="space-y-2">
                <div className="border border-amber-950/60 bg-amber-950/10 p-2 text-[7px] text-amber-400 flex items-center gap-1"><MapPinned size={9} /> Bölgesel açık kaynak görünümü; konum hassasiyeti taktik hedeflemeyi önlemek için düşürülmüştür. Ön cephe veri kümesi kaydı: {String(data.frontline_feature_count || 0)}</div>
                {((data.items as Json[] | undefined) || []).map((item, idx) => {
                  const point = coordinate(item);
                  return <div key={`${String(item.title)}-${idx}`} className="border border-orange-950/60 bg-orange-950/10 p-2">
                    <div className="text-[8px] text-orange-200">{short(item.title, 150)}</div>
                    <div className="text-[7px] text-orange-700 mt-1">{String(item.provider || '')} • {String(item.country || '')} • {String(item.category || '')} • {String(item.severity || '')}</div>
                    <div className="flex gap-2 mt-1">
                      {point && onLocate ? <button onClick={() => onLocate(point[0], point[1])} className="text-[7px] text-amber-300">BÖLGEYİ HARİTADA GÖSTER</button> : null}
                      {item.url ? <a href={String(item.url)} target="_blank" rel="noreferrer" className="text-[7px] text-cyan-400">KAYNAĞI AÇ ↗</a> : null}
                    </div>
                  </div>;
                })}
              </div>
            )}

            {tab === 'health' && (
              <div className="space-y-2">
                <div className="border border-cyan-900/50 bg-cyan-950/10 p-2 flex items-center gap-2">
                  <button disabled={testingAll} onClick={() => void testAllProviders()} className="border border-cyan-700/70 px-2 py-1 text-[7px] text-cyan-200 hover:bg-cyan-950/50">{testingAll ? 'TÜM KAYNAKLAR TEST EDİLİYOR...' : 'TÜM KAYNAKLARI TEST ET'}</button>
                  <span className={`text-[7px] ${testSummary.includes('başarısız') ? 'text-red-400' : 'text-cyan-500'}`}>{testSummary || 'Tazelik, gecikme ve son gerçek bağlantı testi birlikte izlenir.'}</span>
                </div>
                {((data.integrations as HealthRow[] | undefined) || []).map((item) => {
                  const result = testResults[String(item.id)] || (item.last_probe ? (item.last_probe.ok ? `SON TEST BAŞARILI${item.last_probe.latency_ms ? ` • ${item.last_probe.latency_ms} ms` : ''}` : `SON TEST BAŞARISIZ • ${item.last_probe.detail || item.last_probe.status || 'dış servis'}`) : '');
                  const stateClass = item.state === 'live' ? 'text-emerald-400' : item.state === 'stale' ? 'text-red-400' : item.state === 'needs_key' || item.state === 'partial_config' ? 'text-amber-400' : 'text-cyan-400';
                  return <div key={String(item.id)} className={`border bg-black/20 p-2 ${item.state === 'stale' ? 'border-red-900/60' : 'border-cyan-950/70'}`}>
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-[8px] text-white flex items-center gap-1"><ShieldCheck size={9} /> {String(item.name || item.id)}</div>
                        <div className="text-[7px] text-cyan-700 mt-1">{String(item.turkish_category || item.category || '')} • {String(item.turkish_mode || item.mode || '')} • kayıt {Number(item.records || 0).toLocaleString()} • son veri {ageLabel(item.age_seconds)}</div>
                        {item.note ? <div className="text-[7px] text-slate-500 mt-1">{String(item.note)}</div> : null}
                      </div>
                      <div className={`text-[7px] ${stateClass}`}>{String(item.turkish_state || item.state || '')}</div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 mt-2">
                      <button disabled={testing === item.id || testingAll} onClick={() => void testProvider(String(item.id))} className="border border-cyan-800/60 px-2 py-1 text-[7px] hover:bg-cyan-950/40">{testing === item.id ? 'TEST...' : 'BAĞLANTIYI TEST ET'}</button>
                      {item.refreshable ? <button disabled={refreshingProvider === item.id} onClick={() => void refreshProvider(String(item.id))} className="border border-emerald-900/60 px-2 py-1 text-[7px] text-emerald-400 hover:bg-emerald-950/30">{refreshingProvider === item.id ? 'YENİLENİYOR' : 'VERİYİ YENİLE'}</button> : null}
                      {result && <span className={`text-[7px] ${result.includes('BAŞARISIZ') ? 'text-red-400' : 'text-emerald-400'}`}>{result}</span>}
                    </div>
                  </div>;
                })}
                {((data.capabilities as CapabilityRow[] | undefined) || []).length > 0 && <div className="border-t border-cyan-950/70 pt-2 mt-2 space-y-1">
                  <div className="text-[7px] tracking-wider text-cyan-500">YETENEK SINIRLARI / HAZIRLIK</div>
                  {((data.capabilities as CapabilityRow[] | undefined) || []).map((cap) => <div key={String(cap.id)} className="grid grid-cols-[1fr_auto] gap-2 border border-slate-900/80 p-2">
                    <div><div className="text-[8px] text-slate-300">{String(cap.name || cap.id)}</div><div className="text-[7px] text-slate-600 mt-1">{String(cap.detail || '')}</div></div>
                    <div className="text-[7px] text-cyan-500">{String(cap.state || '').toUpperCase()}</div>
                  </div>)}
                </div>}
              </div>
            )}

            {!loading && !error && (tab === 'news' || tab === 'localNews' || tab === 'diplomacy') && !newsRows.length && <div className="text-[8px] text-cyan-700 p-2">Henüz kayıt yok; canlı kaynaklar hazırlanıyor.</div>}
            {!loading && !error && tab === 'cameras' && !((data.items as unknown[] | undefined) || []).length && <div className="text-[8px] text-cyan-700 p-2">Kamu kamera kaynakları henüz veri döndürmedi veya hazırlanıyor.</div>}
            {!loading && !error && tab === 'disasters' && !((data.global as unknown[] | undefined) || []).length && <div className="text-[8px] text-cyan-700 p-2">Afet kaynakları hazırlanıyor.</div>}
          </div>
          <div className="border-t border-cyan-950/60 px-2 py-1 text-[7px] text-cyan-800 flex items-center gap-1"><AlertTriangle size={8} /> Özel/kapalı kameralar, canlı kolluk noktaları, kişi hedefli takip ve gizli/hassas askerî telemetri bu operasyon merkezine dahil edilmez.</div>
        </div>
      )}
    </section>
  );
}
