'use client';

import { useEffect } from 'react';

function isExternalHttp(url: URL): boolean {
  return (url.protocol === 'http:' || url.protocol === 'https:') && url.origin !== window.location.origin;
}

async function openExternal(href: string): Promise<void> {
  const native = window.__SHADOWBROKER_DESKTOP__?.openExternal;
  if (native) {
    // In the packaged desktop, never fall back to navigating the app WebView
    // itself to an external site. The native command is the single authority
    // for leaving the application window and opening the OS default browser.
    await native(href);
    return;
  }
  const opened = window.open(href, '_blank', 'noopener,noreferrer');
  if (!opened) {
    // Browser-only fallback. In native mode this branch is unreachable because
    // `openExternal` is injected by the desktop initialization script.
    window.location.assign(href);
  }
}

/**
 * Desktop-wide external-link adapter.
 *
 * Legacy panels contain a mixture of anchors and window.open calls.  This
 * capture-phase handler guarantees that ordinary http(s) anchors leave the
 * Tauri loopback WebView through the native OS browser while preserving
 * same-origin Gokdogan navigation.
 */
export default function ExternalLinkBridge() {
  useEffect(() => {
    const handler = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const target = event.target as Element | null;
      const anchor = target?.closest?.('a[href]') as HTMLAnchorElement | null;
      if (!anchor) return;
      const raw = anchor.getAttribute('href') || '';
      if (!raw || raw.startsWith('#') || raw.startsWith('javascript:')) return;
      let url: URL;
      try {
        url = new URL(anchor.href, window.location.href);
      } catch {
        return;
      }
      if (!isExternalHttp(url)) return;
      event.preventDefault();
      event.stopPropagation();
      void openExternal(url.href);
    };
    document.addEventListener('click', handler, true);
    return () => document.removeEventListener('click', handler, true);
  }, []);
  return null;
}
