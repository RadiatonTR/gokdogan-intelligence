'use client';

import React, { useEffect, useState } from 'react';
import { Layer, Source } from 'react-map-gl/maplibre';

export default function TrafficRasterOverlay({ enabled }: { enabled: boolean }) {
  const [configured, setConfigured] = useState(false);

  useEffect(() => {
    if (!enabled) {
      setConfigured(false);
      return;
    }
    let cancelled = false;
    fetch('/api/traffic/status', { cache: 'no-store' })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => { if (!cancelled) setConfigured(Boolean(data?.configured)); })
      .catch(() => { if (!cancelled) setConfigured(false); });
    return () => { cancelled = true; };
  }, [enabled]);

  if (!enabled || !configured) return null;
  return (
    <>
      <Source id="gokdogan-traffic-flow" type="raster" tiles={['/api/traffic/tile/flow/{z}/{x}/{y}.png']} tileSize={256} minzoom={0} maxzoom={22}>
        <Layer id="gokdogan-traffic-flow-layer" type="raster" paint={{ 'raster-opacity': 0.72, 'raster-fade-duration': 150 }} />
      </Source>
      <Source id="gokdogan-traffic-incidents" type="raster" tiles={['/api/traffic/tile/incidents/{z}/{x}/{y}.png']} tileSize={256} minzoom={0} maxzoom={22}>
        <Layer id="gokdogan-traffic-incidents-layer" type="raster" paint={{ 'raster-opacity': 0.9, 'raster-fade-duration': 150 }} />
      </Source>
    </>
  );
}
