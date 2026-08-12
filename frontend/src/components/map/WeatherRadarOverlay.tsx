'use client';

import React from 'react';
import { Layer, Source } from 'react-map-gl/maplibre';
import type { Weather } from '@/types/dashboard';

export default function WeatherRadarOverlay({ enabled, weather }: { enabled: boolean; weather?: Weather | null }) {
  if (!enabled || !weather?.time) return null;
  return (
    <Source
      key={`rainviewer-${weather.time}`}
      id="gokdogan-rainviewer-radar"
      type="raster"
      tiles={['/api/weather/radar/tile/{z}/{x}/{y}.png']}
      tileSize={256}
      minzoom={0}
      maxzoom={12}
      attribution="RainViewer"
    >
      <Layer id="gokdogan-rainviewer-radar-layer" type="raster" paint={{ 'raster-opacity': 0.68, 'raster-fade-duration': 250 }} />
    </Source>
  );
}
