'use client';

import React, { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { AlertTriangle, Play, Pause } from 'lucide-react';
import HlsVideo, { type HlsVideoHandle } from '@/components/HlsVideo';

export interface CctvFullscreenModalProps {
  url: string;
  rawUrl?: string;
  mediaType: string;
  isVideo: boolean;
  cameraName: string;
  sourceAgency: string;
  cameraId: string;
  onClose: () => void;
}

export function CctvFullscreenModal({
  url,
  rawUrl = '',
  mediaType,
  isVideo,
  cameraName,
  sourceAgency,
  cameraId,
  onClose,
}: CctvFullscreenModalProps) {
  const [paused, setPaused] = useState(false);
  const [mediaError, setMediaError] = useState(false);
  const [mediaLoaded, setMediaLoaded] = useState(false);
  const [sourceIndex, setSourceIndex] = useState(0);
  const videoRef = useRef<HTMLVideoElement>(null);
  const hlsRef = useRef<HlsVideoHandle>(null);
  const sources = useMemo(() => {
    const seen = new Set<string>();
    return [url, rawUrl]
      .map((candidate) => String(candidate || '').trim())
      .filter((candidate) => {
        if (!candidate || seen.has(candidate)) return false;
        seen.add(candidate);
        return true;
      });
  }, [rawUrl, url]);
  const activeUrl = sources[sourceIndex] || '';

  useEffect(() => {
    setSourceIndex(0);
    setMediaError(false);
    setMediaLoaded(false);
    setPaused(false);
  }, [rawUrl, url]);

  useEffect(() => {
    setMediaLoaded(false);
  }, [activeUrl]);

  const handleMediaFailure = useCallback(() => {
    setSourceIndex((idx) => {
      const next = idx + 1;
      if (next < sources.length) {
        setMediaError(false);
        return next;
      }
      setMediaError(true);
      return idx;
    });
  }, [sources.length]);

  const handleMediaReady = useCallback(() => {
    setMediaLoaded(true);
  }, []);

  useEffect(() => {
    if (sourceIndex !== 0 || sources.length < 2 || mediaLoaded || mediaError) return;
    const timeoutMs = mediaType === 'hls' ? 3200 : 1800;
    const timer = window.setTimeout(() => {
      setSourceIndex((idx) => {
        if (idx !== 0 || mediaLoaded) return idx;
        return 1;
      });
    }, timeoutMs);
    return () => window.clearTimeout(timer);
  }, [mediaError, mediaLoaded, mediaType, sourceIndex, sources.length]);

  const togglePlay = useCallback(() => {
    if (mediaType === 'hls') {
      if (hlsRef.current?.paused) hlsRef.current.play();
      else hlsRef.current?.pause();
      setPaused(!hlsRef.current?.paused);
    } else if (videoRef.current) {
      if (videoRef.current.paused) videoRef.current.play();
      else videoRef.current.pause();
      setPaused(videoRef.current.paused);
    }
  }, [mediaType]);

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 9999,
        background: 'rgba(0,0,0,0.88)',
        backdropFilter: 'blur(8px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '60px 20px 80px 20px',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      onKeyDown={(e: React.KeyboardEvent<HTMLDivElement>) => {
        if (e.key === 'Escape') onClose();
      }}
      tabIndex={-1}
      ref={(el) => el?.focus()}
    >
      <div
        style={{
          background: 'rgba(0,0,0,0.95)',
          border: '1px solid rgba(8,145,178,0.5)',
          borderRadius: 12,
          overflow: 'hidden',
          maxWidth: 'calc(100vw - 40px)',
          maxHeight: 'calc(100vh - 80px)',
          width: 900,
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 0 60px rgba(8,145,178,0.25), inset 0 0 30px rgba(0,0,0,0.5)',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '10px 16px',
            background: 'rgba(8,51,68,0.4)',
            borderBottom: '1px solid rgba(8,145,178,0.3)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <AlertTriangle size={12} style={{ color: '#ef4444' }} />
            <span
              style={{
                fontSize: 11,
                color: '#22d3ee',
                fontFamily: 'monospace',
                letterSpacing: '0.2em',
                fontWeight: 'bold',
              }}
            >
              KAMU KAMERA GÖRÜNTÜLEYİCİ
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span
              style={{
                fontSize: 10,
                color: 'rgba(8,145,178,0.6)',
                fontFamily: 'monospace',
              }}
            >
              ID: {cameraId}
            </span>
            <button
              onClick={onClose}
              style={{
                background: 'rgba(239,68,68,0.2)',
                border: '1px solid rgba(239,68,68,0.4)',
                borderRadius: 6,
                color: '#ef4444',
                fontSize: 10,
                fontFamily: 'monospace',
                padding: '4px 10px',
                cursor: 'pointer',
                letterSpacing: '0.1em',
              }}
            >
              ✕ KAPAT
            </button>
          </div>
        </div>

        {/* Metadata row */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '8px 16px',
            fontSize: 10,
            fontFamily: 'monospace',
            borderBottom: '1px solid rgba(8,51,68,0.5)',
          }}
        >
          <span style={{ color: '#22d3ee', letterSpacing: '0.15em' }}>{sourceAgency}</span>
          <span style={{ color: '#ef4444', letterSpacing: '0.1em', fontWeight: 'bold' }}>
            {mediaType === 'none' ? 'YAYIN YOK' : `CANLI // ${new Date().toLocaleTimeString('tr-TR', { hour12: false })}`}
          </span>
          <span
            style={{
              color: 'rgba(8,145,178,0.7)',
              letterSpacing: '0.1em',
              background: 'rgba(8,145,178,0.1)',
              border: '1px solid rgba(8,145,178,0.2)',
              borderRadius: 4,
              padding: '2px 8px',
            }}
          >
            {mediaType.toUpperCase()}
          </span>
        </div>

        {/* Media area */}
        <div
          style={{
            flex: 1,
            position: 'relative',
            background: '#000',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            minHeight: 400,
            overflow: 'hidden',
          }}
        >
          {activeUrl ? (
            <>
              {mediaType === 'video' && !mediaError && (
                <video
                  key={activeUrl}
                  ref={videoRef}
                  src={activeUrl}
                  autoPlay
                  loop
                  muted
                  playsInline
                  onError={handleMediaFailure}
                  onCanPlay={handleMediaReady}
                  onLoadedData={handleMediaReady}
                  onPlaying={handleMediaReady}
                  style={{
                    maxWidth: '100%',
                    maxHeight: 'calc(100vh - 260px)',
                    objectFit: 'contain',
                    filter: 'contrast(1.25) saturate(0.5)',
                  }}
                />
              )}
              {mediaType === 'hls' && !mediaError && (
                <HlsVideo
                  key={activeUrl}
                  ref={hlsRef}
                  url={activeUrl}
                  onError={handleMediaFailure}
                  onLoaded={handleMediaReady}
                  className="max-w-full max-h-[calc(100vh-260px)] object-contain"
                />
              )}
              {mediaType === 'mjpeg' && (
                <img
                  key={activeUrl}
                  src={activeUrl}
                  alt="MJPEG Feed"
                  style={{
                    maxWidth: '100%',
                    maxHeight: 'calc(100vh - 260px)',
                    objectFit: 'contain',
                    filter: 'contrast(1.25) saturate(0.5)',
                  }}
                  onError={handleMediaFailure}
                  onLoad={handleMediaReady}
                />
              )}
              {(mediaType === 'image' || mediaType === 'satellite') && (
                <img
                  key={activeUrl}
                  src={activeUrl}
                  alt="CCTV Feed"
                  style={{
                    maxWidth: '100%',
                    maxHeight: 'calc(100vh - 260px)',
                    objectFit: 'contain',
                    filter: 'contrast(1.25) saturate(0.5)',
                  }}
                  onError={handleMediaFailure}
                  onLoad={handleMediaReady}
                />
              )}

              {/* Media error fallback */}
              {mediaError && (
                <div style={{ fontSize: 11, color: 'rgba(239,68,68,0.7)', fontFamily: 'monospace', letterSpacing: '0.15em', textAlign: 'center', padding: 40 }}>
                  YAYIN KULLANILAMIYOR<br />
                  <span style={{ fontSize: 9, color: 'rgba(148,163,184,0.5)' }}>proxy ve doğrudan kamu kaynağına erişilemedi</span>
                </div>
              )}

              {/* Live-status overlay */}
              {mediaType !== 'none' && (
                <div
                  style={{
                    position: 'absolute',
                    top: 12,
                    left: 14,
                    fontSize: 9,
                    color: '#22d3ee',
                    background: 'rgba(0,0,0,0.6)',
                    padding: '2px 6px',
                    fontFamily: 'monospace',
                    letterSpacing: '0.1em',
                    borderRadius: 2,
                  }}
                >
                  KAMU YAYINI
                </div>
              )}

              {/* Play/Pause overlay for video streams */}
              {isVideo && (
                <button
                  onClick={togglePlay}
                  style={{
                    position: 'absolute',
                    bottom: 14,
                    right: 14,
                    width: 40,
                    height: 40,
                    borderRadius: '50%',
                    background: 'rgba(0,0,0,0.7)',
                    border: '1px solid rgba(8,145,178,0.5)',
                    color: '#22d3ee',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                  onMouseEnter={(e) => {
                    (e.target as HTMLElement).style.background = 'rgba(8,51,68,0.8)';
                  }}
                  onMouseLeave={(e) => {
                    (e.target as HTMLElement).style.background = 'rgba(0,0,0,0.7)';
                  }}
                >
                  {paused ? <Play size={18} /> : <Pause size={18} />}
                </button>
              )}
            </>
          ) : (
            <div
              style={{
                fontSize: 12,
                color: 'rgba(8,145,178,0.4)',
                fontFamily: 'monospace',
                letterSpacing: '0.2em',
              }}
            >
              <div style={{ textAlign: 'center', maxWidth: 560, lineHeight: 1.8 }}>
                <div style={{ color: '#f59e0b', fontWeight: 'bold' }}>KAMUYA AÇIK YAYIN YOK</div>
                <div style={{ marginTop: 8, fontSize: 10, letterSpacing: '0.08em', color: 'rgba(148,163,184,0.72)' }}>
                  Bu kayıt yalnızca kamuya açık kamera konumu veya metadata bilgisidir. Özel/kapalı kamera akışlarına erişim denenmez.
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Location bar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '10px 16px',
            background: 'rgba(8,51,68,0.3)',
            borderTop: '1px solid rgba(8,145,178,0.2)',
          }}
        >
          <span
            style={{
              fontSize: 10,
              color: '#22d3ee',
              fontFamily: 'monospace',
              letterSpacing: '0.15em',
              fontWeight: 'bold',
            }}
          >
            {cameraName}
          </span>
          <div style={{ display: 'flex', gap: 10 }}>
            {activeUrl && (
              <>
                <a
                  href={rawUrl || activeUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    background: 'rgba(8,145,178,0.2)',
                    border: '1px solid rgba(8,145,178,0.5)',
                    borderRadius: 6,
                    color: '#22d3ee',
                    fontSize: 10,
                    fontFamily: 'monospace',
                    padding: '5px 14px',
                    cursor: 'pointer',
                    textDecoration: 'none',
                    letterSpacing: '0.15em',
                    fontWeight: 'bold',
                  }}
                >
                  KAMU KAYNAĞINI AÇ ↗
                </a>
                <button
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(rawUrl || activeUrl);
                    } catch { /* ignore */ }
                  }}
                  style={{
                    background: 'rgba(8,145,178,0.15)',
                    border: '1px solid rgba(8,145,178,0.4)',
                    borderRadius: 6,
                    color: '#22d3ee',
                    fontSize: 10,
                    fontFamily: 'monospace',
                    padding: '5px 14px',
                    cursor: 'pointer',
                    letterSpacing: '0.15em',
                    fontWeight: 'bold',
                  }}
                >
                  URL KOPYALA
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
