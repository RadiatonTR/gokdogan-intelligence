import type { Metadata } from 'next';
import DesktopBridgeBootstrap from '@/components/DesktopBridgeBootstrap';
import TurkishUiBridge from '@/components/TurkishUiBridge';
import ExternalLinkBridge from '@/components/ExternalLinkBridge';
import MotionRoot from '@/components/MotionRoot';
import { ThemeProvider } from '@/lib/ThemeContext';
import { I18nProvider } from '@/i18n';
import './globals.css';

export const metadata: Metadata = {
  title: 'GOKDOGAN // Küresel İstihbarat Merkezi',
  description: 'Canlı açık kaynak verileriyle küresel durum farkındalığı ve istihbarat panosu',
};

// The dashboard is a live local runtime, not a static landing page. If Next
// prerenders and caches the initial shell, Docker users can get stuck on the
// "prioritizing map feeds" markup before client polling ever hydrates.
export const dynamic = 'force-dynamic';
export const revalidate = 0;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="tr">
      <body className="antialiased bg-[var(--bg-primary)]" suppressHydrationWarning>
        <I18nProvider>
          <ThemeProvider>
            <MotionRoot>
              <DesktopBridgeBootstrap />
              <TurkishUiBridge />
              <ExternalLinkBridge />
              {children}
            </MotionRoot>
          </ThemeProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
