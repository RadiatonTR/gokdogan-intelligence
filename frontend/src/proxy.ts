/**
 * Phase 5F-A: CSP nonce plumbing proxy.
 *
 * Generates a per-request cryptographic nonce and emits a dynamic
 * Content-Security-Policy header for document (page) responses.
 * API routes, static assets, and image optimization paths are excluded.
 */

import { NextRequest, NextResponse } from 'next/server';

function buildCsp(nonce: string, strictScripts = false): string {
  const isDev = process.env.NODE_ENV !== 'production';
  const scriptSrc = isDev
    ? "script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:"
    : strictScripts
      ? `script-src 'self' 'nonce-${nonce}' blob:`
      : "script-src 'self' 'unsafe-inline' blob:";
  const directives = [
    "default-src 'self'",
    scriptSrc,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https:",
    isDev
      ? "connect-src 'self' ws: wss: http://127.0.0.1:8000 http://127.0.0.1:8787 https:"
      : "connect-src 'self' ws: wss: https:",
    "font-src 'self' data:",
    "object-src 'none'",
    "worker-src 'self' blob:",
    "child-src 'self' blob:",
    "frame-src 'self' https://video.ibm.com https://ustream.tv https://www.ustream.tv https://t.me",
    "media-src 'self' blob:",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ];
  return directives.join('; ');
}

export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString('base64');

  // Forward a nonce for staged CSP support. Strict script-src is opt-in until
  // every Next inline bootstrap script is verified with the nonce in production.
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set('x-nonce', nonce);

  const response = NextResponse.next({
    request: { headers: requestHeaders },
  });

  const strictCsp = process.env.SHADOWBROKER_STRICT_CSP === '1';
  response.headers.set('Content-Security-Policy', buildCsp(nonce, strictCsp));
  if (!strictCsp && process.env.NODE_ENV === 'production') {
    response.headers.set('Content-Security-Policy-Report-Only', buildCsp(nonce, true));
  }

  return response;
}

export const config = {
  matcher: [
    /*
     * Match all document/page paths.  Exclude:
     *   - /api/*           (API routes — handled by route handlers)
     *   - /_next/static/*  (static assets)
     *   - /_next/image/*   (image optimization)
     *   - /favicon.ico     (browser icon)
     */
    '/((?!api|_next/static|_next/image|favicon.ico).*)',
  ],
};
