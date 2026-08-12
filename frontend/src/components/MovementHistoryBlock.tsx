'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Route, Timer, Waypoints } from 'lucide-react';

type Payload = {
  status?: string;
  movement?: { duration_minutes?: number; point_count?: number; bearing_deg?: number; current_heading_deg?: number; first_seen_at?: number; last_seen_at?: number };
  route?: { origin_name?: string; dest_name?: string; source?: string };
  notes?: string[];
};

export default function MovementHistoryBlock(props: {
  entityType: 'aircraft' | 'ship';
  icao24?: string;
  callsign?: string;
  registration?: string;
  mmsi?: string | number;
  imo?: string | number;
  name?: string;
}) {
  const [data, setData] = useState<Payload | null>(null);
  const [loading, setLoading] = useState(false);
  const query = useMemo(() => {
    const p = new URLSearchParams({ entity_type: props.entityType });
    if (props.icao24) p.set('icao24', String(props.icao24));
    if (props.callsign) p.set('callsign', String(props.callsign));
    if (props.registration) p.set('registration', String(props.registration));
    if (props.mmsi) p.set('mmsi', String(props.mmsi));
    if (props.imo) p.set('imo', String(props.imo));
    if (props.name) p.set('name', String(props.name));
    return p.toString();
  }, [props.entityType, props.icao24, props.callsign, props.registration, props.mmsi, props.imo, props.name]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`/api/public-intel/entity-movement?${query}`, { cache: 'no-store' })
      .then((r) => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
      .then((payload) => { if (!cancelled) setData(payload); })
      .catch(() => { if (!cancelled) setData(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [query]);

  const movement = data?.movement || {};
  const route = data?.route || {};
  const duration = Number(movement.duration_minutes);
  const points = Number(movement.point_count || 0);

  return (
    <div className="border border-cyan-900/40 bg-cyan-950/10 p-2 space-y-1.5">
      <div className="flex items-center justify-between text-[9px] font-bold text-cyan-300">
        <span className="flex items-center gap-1"><Route size={10} /> CANLI ROTA & HAREKET KAYDI</span>
        <span className="text-[7px] text-cyan-700">{loading ? 'GÜNCELLENİYOR' : data?.status === 'trail_available' ? 'CANLI' : 'BEKLENİYOR'}</span>
      </div>
      <div className="grid grid-cols-2 gap-1 text-[8px]">
        <div className="flex items-center gap-1 text-cyan-600"><Timer size={9} /><span>Gözlenen süre</span></div>
        <div className="text-right text-white">{Number.isFinite(duration) ? `${duration.toFixed(1)} dk` : 'Henüz ölçülmedi'}</div>
        <div className="flex items-center gap-1 text-cyan-600"><Waypoints size={9} /><span>Rota noktası</span></div>
        <div className="text-right text-white">{points || 0}</div>
        <div className="text-cyan-600">Kalkış → varış</div>
        <div className="text-right text-white">{route.origin_name && route.dest_name ? `${route.origin_name} → ${route.dest_name}` : 'Kaynakta bilinmiyor'}</div>
        <div className="text-cyan-600">Gözlenen yön</div>
        <div className="text-right text-white">{Number.isFinite(Number(movement.current_heading_deg ?? movement.bearing_deg)) ? `${Number(movement.current_heading_deg ?? movement.bearing_deg).toFixed(0)}°` : '—'}</div>
        <div className="text-cyan-600">İlk / son gözlem</div>
        <div className="text-right text-white">{movement.first_seen_at && movement.last_seen_at ? `${new Date(movement.first_seen_at * 1000).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })} / ${new Date(movement.last_seen_at * 1000).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })}` : '—'}</div>
      </div>
      {(data?.notes || []).slice(0, 1).map((note) => <div key={note} className="text-[7px] leading-relaxed text-cyan-800">{note}</div>)}
    </div>
  );
}
