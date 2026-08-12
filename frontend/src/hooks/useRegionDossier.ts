import { useCallback, useState, useEffect } from 'react';
import type { RegionDossier, SelectedEntity } from '@/types/dashboard';
import { API_BASE } from '@/lib/api';

// ─── CACHE ─────────────────────────────────────────────────────────────────
const _dossierCache = new Map<string, { data: RegionDossier; ts: number }>();
const CACHE_TTL = 86400_000;

function getCached(lat: number, lng: number): RegionDossier | null {
  const key = `${Math.round(lat * 10) / 10}_${Math.round(lng * 10) / 10}`;
  const entry = _dossierCache.get(key);
  if (entry && Date.now() - entry.ts < CACHE_TTL) return entry.data;
  if (entry) _dossierCache.delete(key);
  return null;
}

function setCache(lat: number, lng: number, data: RegionDossier) {
  const key = `${Math.round(lat * 10) / 10}_${Math.round(lng * 10) / 10}`;
  _dossierCache.set(key, { data, ts: Date.now() });
  if (_dossierCache.size > 500) {
    const oldest = _dossierCache.keys().next().value;
    if (oldest) _dossierCache.delete(oldest);
  }
}

function buildLocalSentinelFallback(lat: number, lng: number) {
  const latSpan = 0.18;
  const lngSpan = 0.24;
  const bbox = `${lng - lngSpan},${lat - latSpan},${lng + lngSpan},${lat + latSpan}`;
  const base =
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export';
  return {
    found: true,
    scene_id: null,
    datetime: null,
    cloud_cover: null,
    thumbnail_url: `${base}?bbox=${bbox}&bboxSR=4326&imageSR=4326&size=640,360&format=png32&f=image`,
    fullres_url: `${base}?bbox=${bbox}&bboxSR=4326&imageSR=4326&size=1600,900&format=png32&f=image`,
    bbox: [lng - lngSpan, lat - latSpan, lng + lngSpan, lat + latSpan],
    platform: 'Esri World Imagery',
    fallback: true,
    message: 'Using local imagery fallback while live satellite search completes.',
  };
}

function buildLimitedDossier(lat: number, lng: number, error?: string): RegionDossier {
  return {
    lat,
    lng,
    coordinates: { lat, lng },
    location: {
      display_name: `${lat.toFixed(4)}, ${lng.toFixed(4)}`,
    },
    country: {
      name: 'LIMITED INTEL',
      official_name: '',
      leader: 'Unknown',
      government_type: 'Unavailable',
      population: 0,
      capital: 'Unknown',
      languages: [],
      currencies: [],
      region: '',
      subregion: '',
      area_km2: 0,
      flag_emoji: '',
    },
    local: {
      name: 'Selected coordinates',
      state: '',
      description: 'Fallback dossier',
      summary:
        'Live region enrichment is currently unavailable or slow. Local coordinates and fallback imagery are still available.',
      thumbnail: '',
    },
    warning: error || 'Region dossier is using local fallback data.',
  } as RegionDossier;
}

/** Self-hosted backend routes (#351) — no browser-direct third-party dossier calls. */
async function fetchDossierBundle(
  lat: number,
  lng: number,
): Promise<{ dossier: Record<string, unknown> | null; sentinel2: Record<string, unknown> }> {
  const qs = `lat=${encodeURIComponent(lat)}&lng=${encodeURIComponent(lng)}`;
  const [dossierRes, sentinelRes] = await Promise.allSettled([
    fetch(`${API_BASE}/api/region-dossier?${qs}`),
    fetch(`${API_BASE}/api/sentinel2/search?${qs}`),
  ]);

  let dossier: Record<string, unknown> | null = null;
  if (dossierRes.status === 'fulfilled' && dossierRes.value.ok) {
    dossier = await dossierRes.value.json();
  } else if (dossierRes.status === 'fulfilled') {
    console.warn('[Dossier] Backend region-dossier HTTP', dossierRes.value.status);
  } else {
    console.warn('[Dossier] Backend region-dossier failed:', dossierRes.reason);
  }

  let sentinel2: Record<string, unknown> = buildLocalSentinelFallback(lat, lng);
  if (sentinelRes.status === 'fulfilled' && sentinelRes.value.ok) {
    sentinel2 = await sentinelRes.value.json();
  } else if (sentinelRes.status === 'rejected') {
    console.warn('[Dossier] Backend sentinel2/search failed:', sentinelRes.reason);
  }

  return { dossier, sentinel2 };
}

function dossierFromBackend(
  lat: number,
  lng: number,
  raw: Record<string, unknown>,
  sentinel2: Record<string, unknown>,
): RegionDossier {
  const coords = (raw.coordinates as { lat?: number; lng?: number }) || { lat, lng };
  return {
    lat,
    lng,
    coordinates: coords,
    location: raw.location ?? {},
    country: raw.country ?? null,
    local: raw.local ?? null,
    error: raw.error as string | undefined,
    warning: raw.warning as string | undefined,
    sentinel2,
  } as RegionDossier;
}

export function useRegionDossier(
  selectedEntity: SelectedEntity | null,
  setSelectedEntity: (entity: SelectedEntity | null) => void,
) {
  const [regionDossier, setRegionDossier] = useState<RegionDossier | null>(null);
  const [regionDossierLoading, setRegionDossierLoading] = useState(false);

  const handleMapRightClick = useCallback(
    async (coords: { lat: number; lng: number }) => {
      const { lat, lng } = coords;
      const esriFallback = buildLocalSentinelFallback(lat, lng);

      setSelectedEntity({
        type: 'region_dossier',
        id: `${lat.toFixed(4)}_${lng.toFixed(4)}`,
        extra: coords,
      });
      setRegionDossierLoading(true);

      const cached = getCached(lat, lng);
      if (cached) {
        setRegionDossier(cached);
        setRegionDossierLoading(false);
        return;
      }

      setRegionDossier({
        ...buildLimitedDossier(lat, lng),
        sentinel2: esriFallback,
      });

      try {
        const { dossier, sentinel2 } = await fetchDossierBundle(lat, lng);

        if (!dossier) {
          setRegionDossier({
            ...buildLimitedDossier(lat, lng, 'Region dossier unavailable — check backend connection'),
            sentinel2,
          });
          return;
        }

        const result = dossierFromBackend(lat, lng, dossier, sentinel2);
        setRegionDossier(result);
        setCache(lat, lng, result);
      } catch (e) {
        console.error('[Dossier] Unexpected error:', e);
        setRegionDossier({
          ...buildLimitedDossier(lat, lng, 'Region dossier request failed unexpectedly'),
          sentinel2: esriFallback,
        });
      } finally {
        setRegionDossierLoading(false);
      }
    },
    [setSelectedEntity],
  );

  useEffect(() => {
    if (selectedEntity?.type !== 'region_dossier') {
      setRegionDossier(null);
      setRegionDossierLoading(false);
    }
  }, [selectedEntity]);

  return { regionDossier, regionDossierLoading, handleMapRightClick };
}
