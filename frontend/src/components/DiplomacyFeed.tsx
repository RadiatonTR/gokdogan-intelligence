'use client';

import { useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, ExternalLink, Landmark } from 'lucide-react';
import { useDataKey } from '@/hooks/useDataStore';
import type { NewsArticle } from '@/types/dashboard';

const DIPLOMACY_RE = /\b(treaty|agreement|accord|pact|memorandum|mou|ceasefire|armistice|bilateral|multilateral|diplomatic|sanctions? deal|trade deal|peace deal|summit)\b|\b(antlaşma|anlaşma|mutabakat|protokol|ateşkes|diplomasi|diplomatik|ikili görüşme|çok taraflı|barış anlaşması|ticaret anlaşması|zirve)\b/i;

export default function DiplomacyFeed() {
  const news = useDataKey('news') as NewsArticle[] | undefined;
  const [open, setOpen] = useState(false);

  const items = useMemo(() => (news ?? [])
    .filter((article) => DIPLOMACY_RE.test(`${article.title || ''} ${article.summary || ''}`))
    .sort((a, b) => {
      const risk = (b.risk_score || 0) - (a.risk_score || 0);
      if (risk) return risk;
      return Date.parse(b.pub_date || '') - Date.parse(a.pub_date || '');
    })
    .slice(0, 8), [news]);

  return (
    <section className="flex-shrink-0 border border-cyan-900/40 bg-[#0a0a0a]/90 font-mono">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="w-full flex items-center justify-between gap-2 px-3 py-2 text-left hover:bg-cyan-950/25 transition-colors"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2 min-w-0">
          <Landmark size={12} className="text-cyan-400 shrink-0" />
          <span className="text-[10px] tracking-[0.16em] text-cyan-300 font-bold truncate">DİPLOMASİ & ANLAŞMALAR</span>
          <span className="text-[8px] text-[var(--text-muted)] border border-cyan-900/40 px-1 rounded">{items.length}</span>
        </span>
        {open ? <ChevronUp size={12} className="text-cyan-500" /> : <ChevronDown size={12} className="text-cyan-500" />}
      </button>

      {open && (
        <div className="max-h-56 overflow-y-auto styled-scrollbar border-t border-cyan-900/30">
          {items.length === 0 ? (
            <div className="px-3 py-3 text-[9px] text-[var(--text-muted)] leading-relaxed">
              Mevcut canlı haber akışında antlaşma, anlaşma, mutabakat veya diplomatik anlaşma eşleşmesi yok.
            </div>
          ) : items.map((article) => (
            <article key={String(article.id)} className="px-3 py-2 border-b border-cyan-900/20 last:border-b-0 hover:bg-cyan-950/15">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-[9px] text-[var(--text-primary)] leading-snug line-clamp-2">{article.title}</div>
                  <div className="mt-1 text-[8px] text-[var(--text-muted)] flex gap-2 flex-wrap">
                    <span>{article.source || 'kaynak bilinmiyor'}</span>
                    {article.region && <span>• {article.region}</span>}
                    {article.pub_date && <span>• {new Date(article.pub_date).toLocaleString('tr-TR')}</span>}
                  </div>
                </div>
                {article.link && (
                  <a
                    href={article.link}
                    target="_blank"
                    rel="noopener noreferrer"
                    title="Kaynağı yeni sekmede aç"
                    className="text-cyan-500 hover:text-cyan-300 shrink-0"
                  >
                    <ExternalLink size={11} />
                  </a>
                )}
              </div>
            </article>
          ))}
          <div className="px-3 py-2 text-[7.5px] text-[var(--text-muted)]/70">
            Bu görünüm mevcut haber akışındaki anahtar kelime eşleşmelerini ayırır; resmî belge statüsü kaynak bağlantısından doğrulanmalıdır.
          </div>
        </div>
      )}
    </section>
  );
}
