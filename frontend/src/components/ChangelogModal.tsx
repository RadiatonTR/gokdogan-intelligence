'use client';

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from '@/lib/motion';
import {
  X,
  Network,
  KeyRound,
  Shield,
  Bug,
  Heart,
  MessageSquare,
  Radio,
  Radar,
  Plane,
  Languages,
  Layers,
  Bot,
} from 'lucide-react';

const CURRENT_VERSION = '1.0.0';
const STORAGE_KEY = `shadowbroker_changelog_v${CURRENT_VERSION}`;
const RELEASE_TITLE = 'Gökdoğan Intelligence v1.0.0 — İlk Resmî Sürüm';

const HEADLINE_FEATURES = [
  {
    icon: <Radar size={20} className="text-purple-400" />,
    accent: 'purple' as const,
    title: 'Stratejik Risk ve Analiz Katmanı',
    subtitle:
      'Kamuya açık verileri, risk puanlama ve katman bindirmeleriyle harita üzerinde birlikte değerlendiren stratejik analiz görünümü.',
    details: [
      'Canlı risk göstergeleri harita üzerine işlenir; farklı OSINT akışları aynı çalışma yüzeyinde karşılaştırılabilir.',
      'Varlık profilleri ve iz görünümü, desteklenen yerel analiz araçlarıyla aynı komuta yüzeyinde incelenebilir.',
      'Katman seçimleri, eşikler ve panel durumu yerel tercihlerde korunur.',
    ],
    callToAction: 'SOL PANEL → KATMANLAR → STRATEJİK RİSK',
  },
  {
    icon: <MessageSquare size={20} className="text-cyan-400" />,
    accent: 'cyan' as const,
    title: 'OSINT İçerik ve Kaynak Bağlantıları',
    subtitle:
      'Kaynak bağlantıları ve desteklenen içerik akışları harita bağlamında gösterilir; kaynak dili bilgisi korunur.',
    details: [
      'Desteklenen içeriklerde kaynak dili tespit edilir ve yerelleştirme katmanı kullanılabilir.',
      'Kamu sürümünün kullanıcı arayüzü Türkçe olarak sabitlenmiştir.',
      'Kaynak rozetleri, verinin hangi sağlayıcıdan geldiğini görünür tutar.',
    ],
    callToAction: 'HARİTA → KAYNAK → AYRINTIYI AÇ',
  },
  {
    icon: <Plane size={20} className="text-amber-400" />,
    accent: 'cyan' as const,
    title: 'Havacılık ve Küresel Telemetri',
    subtitle:
      'Kamuya açık havacılık telemetrisi, uygun olduğunda uçak ayrıntıları, gözlenen iz ve veri bağlantısı zenginleştirmeleriyle sunulur.',
    details: [
      'Desteklenen ACARS verileri hava aracı profiline bağlanır ve uygun yerel özetleme kullanılabilir.',
      'Hareketli varlık bütçesi çalışma profiline göre yönetilir; yoğun bölgelerde görünürlük kontrollü biçimde ölçeklenir.',
      'Artımlı canlı veri güncellemeleri ve harita çizim iyileştirmeleri yüksek yenileme hızında titreşimi azaltır.',
    ],
    callToAction: 'HARİTA → HAVA ARACI → AYRINTILARI AÇ',
  },
];

const R22_FEATURES = [
  { icon: <Shield size={18} className="text-green-400" />, title: 'Windows Yayın Kapısı', desc: 'Derleme, test, paketleme ve kurulu çalışma zamanı doğrulaması tek zincirde çalışır.' },
  { icon: <Shield size={18} className="text-amber-400" />, title: 'İzole Python 3.12 Çalışma Alanı', desc: 'Backend testleri kilitli bağımlılıklarla geçici ve izole Python ortamında çalıştırılır.' },
  { icon: <KeyRound size={18} className="text-cyan-400" />, title: 'Güvenli Test Temizliği', desc: 'Geçici test ortamları ve çalışma verileri başarısızlık durumunda dahi kaynak ağacından temizlenir.' },
  { icon: <Layers size={18} className="text-purple-400" />, title: 'Birikimli Sağlamlaştırma', desc: 'Runtime SHA-256 doğrulaması, kilitli bağımlılıklar, npm güvenlik kapıları ve kaynak bütünlüğü kontrolleri korunur.' },
];

const NEW_FEATURES = [
  ...R22_FEATURES,
  {
    icon: <Languages size={18} className="text-purple-400" />,
    title: 'Türkçe Arayüz',
    desc: 'Kamu sürümünde kullanıcı arayüzü Türkçe olarak sunulur; sağlayıcı ve teknik kimlikler özgün biçimde korunur.',
  },
  {
    icon: <Layers size={18} className="text-cyan-400" />,
    title: 'Kaydedilen Pano Düzeni',
    desc: 'Katmanlar, filtreler, harita stili ve bölüm durumları yerel olarak korunur.',
  },
  {
    icon: <Bot size={18} className="text-green-400" />,
    title: 'Yerel Analiz Güvenliği',
    desc: 'Yerel analiz ve entegrasyon yüzeylerinde sağlık kontrolleri, yetkilendirme ve güvenli bağlantı sınırları uygulanır.',
  },
  {
    icon: <Radio size={18} className="text-amber-400" />,
    title: 'SAR ve Mesh Hazırlığı',
    desc: 'SAR katmanı, mesh çalışma alanı ve artımlı canlı veri akışı daha kararlı harita güncellemeleri için bütünleştirilmiştir.',
  },
  {
    icon: <Network size={18} className="text-cyan-400" />,
    title: 'Infonet Kararlılığı',
    desc: 'Infonet yönlendirme ve çalışma alanı kararlılığı iyileştirildi.',
  },
  {
    icon: <Shield size={18} className="text-green-400" />,
    title: 'Güvenlik ve Kararlılık',
    desc: 'Oturum belirteçleri, eşzamanlı veri işleme ve yerel anlık görüntü işlemleri sağlamlaştırıldı.',
  },
];

const BUG_FIXES = [
  'Eşzamanlı GDELT veri işleme yarış durumu giderildi.',
  'Yük altında yerel anlık görüntü tutarlılığı güçlendirildi.',
  'İspanya DGT kamu kamera uç noktası yönlendirmesi düzeltildi.',
  'RSS alımı için feedparser uyumluluğu iyileştirildi.',
  'Katman tercihlerinin açılışta kaydedilmiş durumu ezmesi engellendi.',
  'Infonet sekme yönlendirme regresyonu giderildi.',
];

type ChangelogContributor = {
  name: string;
  desc: string;
  pr?: string;
};

const CONTRIBUTORS: ChangelogContributor[] = [
  {
    name: 'esmaeelE',
    desc: 'Yerelleştirme ve dokümantasyon katkıları',
    pr: '#472, #393',
  },
  {
    name: 'nzinci',
    desc: 'Entegrasyon sağlık uç noktası katkısı',
    pr: '#470',
  },
  {
    name: 'Javier Andreo Zapata',
    desc: 'İspanya DGT kamu kamera uç noktası düzeltmesi',
    pr: '#413',
  },
  {
    name: 'TheYellowBeanieGuy',
    desc: 'Eşzamanlı veri işleme ve anlık görüntü sağlamlaştırması',
    pr: '#388, #389',
  },
  {
    name: 'anntr1k3',
    desc: 'Harita ve frontend dokümantasyonu katkısı',
    pr: '#435',
  },
];

export function useChangelog() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    const seen = localStorage.getItem(STORAGE_KEY);
    if (!seen) setShow(true);
  }, []);
  return { showChangelog: show, setShowChangelog: setShow };
}

interface ChangelogModalProps {
  onClose: () => void;
}

const ChangelogModal = React.memo(function ChangelogModal({ onClose }: ChangelogModalProps) {
  const handleDismiss = () => {
    localStorage.setItem(STORAGE_KEY, 'true');
    onClose();
  };

  return (
    <AnimatePresence>
      <motion.div
        key="changelog-backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black/80 backdrop-blur-sm z-[10000]"
        onClick={handleDismiss}
      />
      <motion.div
        key="changelog-modal"
        initial={{ opacity: 0, scale: 0.9, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.9, y: 20 }}
        transition={{ type: 'spring', damping: 25, stiffness: 300 }}
        className="fixed inset-0 z-[10001] flex items-center justify-center pointer-events-none"
      >
        <div
          className="w-[700px] max-h-[90vh] bg-[var(--bg-secondary)]/98 border border-cyan-900/50 pointer-events-auto flex flex-col overflow-hidden"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="p-5 pb-3 border-b border-[var(--border-primary)]/80">
            <div className="flex items-center justify-between">
              <div>
                <div className="flex items-center gap-3">
                  <div className="px-2.5 py-1 bg-cyan-500/15 border border-cyan-500/30 text-xs font-mono font-bold text-cyan-400 tracking-widest">
                    v{CURRENT_VERSION}
                  </div>
                  <h2 className="text-base font-bold tracking-[0.15em] text-[var(--text-primary)] font-mono">
                    YENİLİKLER
                  </h2>
                </div>
                <p className="text-[11px] text-cyan-500/70 font-mono tracking-widest mt-1">
                  {RELEASE_TITLE.toUpperCase()}
                </p>
              </div>
              <button
                onClick={handleDismiss}
                className="w-8 h-8 border border-[var(--border-primary)] hover:border-red-500/50 flex items-center justify-center text-[var(--text-muted)] hover:text-red-400 transition-all hover:bg-red-950/20"
              >
                <X size={14} />
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto styled-scrollbar p-5 space-y-5">
            {HEADLINE_FEATURES.map((h, idx) => {
              const isPurple = h.accent === 'purple';
              const cardClass = isPurple
                ? 'border border-purple-500/30 bg-purple-950/20 p-4 space-y-3'
                : 'border border-cyan-500/30 bg-cyan-950/20 p-4 space-y-3';
              const iconWrapClass = isPurple
                ? 'w-9 h-9 border border-purple-500/40 bg-purple-500/10 flex items-center justify-center flex-shrink-0'
                : 'w-9 h-9 border border-cyan-500/40 bg-cyan-500/10 flex items-center justify-center flex-shrink-0';
              const titleClass = isPurple
                ? 'text-sm font-mono text-purple-300 font-bold tracking-wide'
                : 'text-sm font-mono text-cyan-300 font-bold tracking-wide';
              const subtitleClass = isPurple
                ? 'text-xs font-mono text-purple-500/80 mt-0.5'
                : 'text-xs font-mono text-cyan-500/80 mt-0.5';
              const ctaClass = isPurple
                ? 'text-[11px] font-mono text-purple-400 tracking-[0.25em] font-bold'
                : 'text-[11px] font-mono text-cyan-400 tracking-[0.25em] font-bold';

              return (
                <div key={idx} className={cardClass}>
                  <div className="flex items-center gap-3">
                    <div className={iconWrapClass}>{h.icon}</div>
                    <div>
                      <div className={titleClass}>{h.title}</div>
                      <div className={subtitleClass}>{h.subtitle}</div>
                    </div>
                  </div>

                  <div className="space-y-2">
                    {h.details.map((para, i) => (
                      <p
                        key={i}
                        className="text-xs font-mono text-[var(--text-secondary)] leading-relaxed"
                      >
                        {para}
                      </p>
                    ))}
                  </div>

                  <div className="text-center pt-1">
                    <span className={ctaClass}>{h.callToAction}</span>
                  </div>
                </div>
              );
            })}

            {/* R22 desktop trust note */}
            <div className="border border-green-500/30 bg-green-950/15 p-3 flex items-start gap-3">
              <Shield size={18} className="text-green-400 mt-0.5 flex-shrink-0" />
              <div className="space-y-1">
                <div className="text-xs font-mono text-green-300 font-bold tracking-wide uppercase">
                  Doğrulanmış masaüstü çalışma zamanı
                </div>
                <div className="text-xs font-mono text-green-200/80 leading-relaxed">
                  Paketli backend çalıştırılmadan önce dosya bazlı SHA-256 manifestiyle doğrulanır; yönetilen çalışma zamanı eşitleme sonrasında yeniden denetlenir. İmzalı özel bir yayın kanalı açıkça yapılandırılmadıkça genel güncelleyici varsayılan olarak kapalı kalır.
                </div>
              </div>
            </div>

            {/* Other New Features */}
            <div>
              <div className="text-xs font-mono tracking-[0.2em] text-cyan-400 font-bold mb-3 flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
                YENİ YETENEKLER
              </div>
              <div className="space-y-2">
                {NEW_FEATURES.map((f) => (
                  <div
                    key={f.title}
                    className="flex items-start gap-3 p-3 border border-[var(--border-primary)]/50 bg-[var(--bg-primary)]/30 hover:border-[var(--border-secondary)] transition-colors"
                  >
                    <div className="mt-0.5 flex-shrink-0">{f.icon}</div>
                    <div>
                      <div className="text-[13px] font-mono text-[var(--text-primary)] font-bold">
                        {f.title}
                      </div>
                      <div className="text-xs font-mono text-[var(--text-muted)] leading-relaxed mt-0.5">
                        {f.desc}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Bug Fixes */}
            <div>
              <div className="text-xs font-mono tracking-[0.2em] text-green-400 font-bold mb-3 flex items-center gap-2">
                <Bug size={14} className="text-green-400" />
                DÜZELTMELER VE İYİLEŞTİRMELER
              </div>
              <div className="space-y-1.5">
                {BUG_FIXES.map((fix, i) => (
                  <div key={i} className="flex items-start gap-2 px-3 py-1.5">
                    <span className="text-green-500 text-xs mt-0.5 flex-shrink-0">+</span>
                    <span className="text-xs font-mono text-[var(--text-secondary)] leading-relaxed">
                      {fix}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Contributors */}
            <div>
              <div className="text-xs font-mono tracking-[0.2em] text-pink-400 font-bold mb-3 flex items-center gap-2">
                <Heart size={14} className="text-pink-400" />
                KATKILAR VE TEŞEKKÜR
              </div>
              <div className="space-y-1.5">
                {CONTRIBUTORS.map((c, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-2 px-3 py-2 border border-pink-500/20 bg-pink-500/5"
                  >
                    <span className="text-pink-400 text-xs mt-0.5 flex-shrink-0">&hearts;</span>
                    <div>
                      <span className="text-[13px] font-mono text-pink-300 font-bold">
                        {c.name}
                      </span>
                      <span className="text-xs font-mono text-[var(--text-muted)]">
                        {' '}
                        &mdash; {c.desc}
                      </span>
                      {c.pr && (
                        <span className="text-[11px] font-mono text-[var(--text-muted)]">
                          {' '}
                          (PR {c.pr})
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="p-4 border-t border-[var(--border-primary)]/80 flex items-center justify-center">
            <button
              onClick={handleDismiss}
              className="px-8 py-2.5 bg-cyan-500/15 border border-cyan-500/40 text-cyan-400 hover:bg-cyan-500/25 text-xs font-mono tracking-[0.2em] transition-all"
            >
              TAMAM
            </button>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
});

export default ChangelogModal;
