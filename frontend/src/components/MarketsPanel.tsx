'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { motion, AnimatePresence } from '@/lib/motion';
import {
  ArrowDownRight,
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  Coins,
  ExternalLink,
  Landmark,
  RefreshCw,
  Settings,
  ShieldCheck,
  TrendingUp,
  UserCheck,
  WalletCards,
} from 'lucide-react';
import type { DashboardData, StockTicker } from '@/types/dashboard';
import type { CongressTrade, InsiderTransaction } from '@/types/unusualWhales';
import { fetchCongressTrades, fetchInsiderTransactions, fetchUWStatus } from '@/lib/uwClient';

type Tab = 'overview' | 'fx' | 'metals' | 'crypto' | 'congress' | 'insider';

const TAB_CONFIG: { key: Tab; label: string; icon: React.ReactNode }[] = [
  { key: 'overview', label: 'PİYASA', icon: <TrendingUp size={10} /> },
  { key: 'fx', label: 'DÖVİZ', icon: <WalletCards size={10} /> },
  { key: 'metals', label: 'MADEN', icon: <Coins size={10} /> },
  { key: 'crypto', label: 'KRİPTO', icon: <ShieldCheck size={10} /> },
  { key: 'congress', label: 'KONGRE', icon: <Landmark size={10} /> },
  { key: 'insider', label: 'İÇERİDEN', icon: <UserCheck size={10} /> },
];

function chamberBadge(chamber: string) {
  const c = chamber?.toLowerCase();
  if (c === 'senator' || c === 'senate') return 'S';
  if (c === 'representative' || c === 'house') return 'T';
  return c?.charAt(0)?.toUpperCase() || '?';
}

function txColor(tx: string) {
  const t = tx?.toLowerCase() || '';
  if (t.includes('purchase') || t.includes('buy')) return 'text-green-400';
  if (t.includes('sale') || t.includes('sell')) return 'text-red-400';
  return 'text-yellow-400';
}

function transactionLabel(value: string) {
  const v = (value || '').toLowerCase();
  if (v.includes('purchase') || v.includes('buy')) return 'ALIM';
  if (v.includes('sale') || v.includes('sell')) return 'SATIM';
  return value || '—';
}

function insiderCodeLabel(code: string) {
  const map: Record<string, string> = {
    P: 'Alım',
    S: 'Satım',
    A: 'Tahsis',
    M: 'Opsiyon Kullanımı',
    F: 'Vergi',
    G: 'Hediye',
    C: 'Dönüşüm',
    X: 'Sona Erme',
  };
  return map[code?.toUpperCase()] || code || '—';
}

function formatPrice(price: number, mode: 'usd' | 'plain' = 'usd') {
  const digits = Math.abs(price) < 10 ? 4 : 2;
  const formatted = (price ?? 0).toLocaleString('tr-TR', {
    minimumFractionDigits: Math.min(2, digits),
    maximumFractionDigits: digits,
  });
  return mode === 'usd' ? `$${formatted}` : formatted;
}

function QuoteRow({
  ticker,
  info,
  priceMode = 'usd',
}: {
  ticker: string;
  info: StockTicker;
  priceMode?: 'usd' | 'plain';
}) {
  return (
    <div className="flex items-center justify-between border border-cyan-500/10 bg-cyan-950/10 p-1.5 rounded-sm">
      <div className="min-w-0">
        <div className="font-bold text-cyan-300 text-[10px] truncate">{ticker}</div>
        {info.symbol && (
          <div className="text-[8px] text-[var(--text-muted)]/60 truncate">{info.symbol}</div>
        )}
      </div>
      <div className="flex items-center gap-3 text-right">
        <span className="text-[var(--text-primary)] font-bold text-xs">
          {formatPrice(info.price ?? 0, priceMode)}
        </span>
        <span
          className={`flex items-center gap-0.5 w-14 justify-end text-[9px] ${
            info.up ? 'text-cyan-400' : 'text-red-400'
          }`}
        >
          {info.up ? <ArrowUpRight size={10} /> : <ArrowDownRight size={10} />}
          {Math.abs(info.change_percent ?? 0).toFixed(2)}%
        </span>
      </div>
    </div>
  );
}

function QuoteSection({
  title,
  quotes,
  priceMode = 'usd',
}: {
  title: string;
  quotes: Record<string, StockTicker>;
  priceMode?: 'usd' | 'plain';
}) {
  const entries = Object.entries(quotes || {});
  if (!entries.length) return null;
  return (
    <div>
      <h3 className="text-[9px] font-bold tracking-widest text-cyan-400 mb-1.5">{title}</h3>
      <div className="flex flex-col gap-1">
        {entries.map(([ticker, info]) => (
          <QuoteRow key={ticker} ticker={ticker} info={info} priceMode={priceMode} />
        ))}
      </div>
    </div>
  );
}

function EmptyMarketState() {
  return (
    <div className="text-[var(--text-muted)] text-[10px] py-4 text-center leading-relaxed">
      Canlı piyasa verisi bekleniyor. Gokdogan masaüstü başlatıcısı canlı veri profilini otomatik açar.
    </div>
  );
}

function CongressTab({ trades }: { trades: CongressTrade[] }) {
  if (!trades.length) {
    return <div className="text-[var(--text-muted)] text-[10px] py-4 text-center">Yeni kongre işlemi bulunamadı.</div>;
  }
  return (
    <div className="flex flex-col gap-1.5">
      {trades.slice(0, 20).map((t, i) => (
        <div key={`${t.politician_name}-${i}`} className="border border-cyan-500/10 bg-cyan-950/10 p-1.5 rounded-sm">
          <div className="flex items-center justify-between gap-1">
            <div className="flex items-center gap-1.5 min-w-0">
              <span className="text-[9px] font-bold text-cyan-300 bg-cyan-900/40 px-1 rounded flex-shrink-0">
                {chamberBadge(t.chamber)}
              </span>
              <span className="text-[10px] text-[var(--text-primary)] truncate font-medium">{t.politician_name}</span>
            </div>
            {t.ticker && <span className="text-[10px] font-bold text-cyan-400 flex-shrink-0">{t.ticker}</span>}
          </div>
          <div className="flex items-center justify-between mt-0.5">
            <span className={`text-[9px] ${txColor(t.transaction_type || '')}`}>
              {transactionLabel(t.transaction_type || '')}
            </span>
            <div className="flex items-center gap-2">
              {t.amount_range && <span className="text-[9px] text-[var(--text-muted)]">{t.amount_range}</span>}
              {t.filing_date && <span className="text-[9px] text-[var(--text-muted)]">{t.filing_date}</span>}
            </div>
          </div>
          {t.asset_name && t.asset_name !== t.ticker && (
            <div className="text-[11px] text-[var(--text-muted)]/70 truncate mt-0.5">{t.asset_name}</div>
          )}
        </div>
      ))}
    </div>
  );
}

function InsiderTab({ transactions }: { transactions: InsiderTransaction[] }) {
  if (!transactions.length) {
    return <div className="text-[var(--text-muted)] text-[10px] py-4 text-center">Yeni içeriden işlem bulunamadı.</div>;
  }
  return (
    <div className="flex flex-col gap-1.5">
      {transactions.slice(0, 20).map((t, i) => {
        const isBuy = t.transaction_code === 'P';
        const isSell = t.transaction_code === 'S';
        return (
          <div key={`${t.name}-${i}`} className="border border-cyan-500/10 bg-cyan-950/10 p-1.5 rounded-sm">
            <div className="flex items-center justify-between gap-1">
              <span className="text-[10px] text-[var(--text-primary)] truncate font-medium">{t.name}</span>
              <span className="text-[10px] font-bold text-cyan-400 flex-shrink-0">{t.ticker}</span>
            </div>
            <div className="flex items-center justify-between mt-0.5">
              <span className={`text-[9px] font-bold ${isBuy ? 'text-green-400' : isSell ? 'text-red-400' : 'text-yellow-400'}`}>
                {insiderCodeLabel(t.transaction_code || '')}
              </span>
              <div className="flex items-center gap-2">
                {t.change !== 0 && (
                  <span className={`text-[9px] ${t.change > 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {t.change > 0 ? '+' : ''}{t.change.toLocaleString('tr-TR')} hisse
                  </span>
                )}
                {t.transaction_price > 0 && (
                  <span className="text-[9px] text-[var(--text-muted)]">${t.transaction_price.toFixed(2)}</span>
                )}
              </div>
            </div>
            {t.filing_date && <div className="text-[11px] text-[var(--text-muted)]/70 mt-0.5">{t.filing_date}</div>}
          </div>
        );
      })}
    </div>
  );
}

interface MarketsPanelProps {
  data: DashboardData;
  focused?: boolean;
  onFocusChange?: (focused: boolean) => void;
}

const MarketsPanel = React.memo(function MarketsPanel({ data, focused, onFocusChange }: MarketsPanelProps) {
  const [isMinimized, setIsMinimized] = useState(!focused);
  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const [finnhubConfigured, setFinnhubConfigured] = useState<boolean | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [localCongress, setLocalCongress] = useState<CongressTrade[] | null>(null);
  const [localInsider, setLocalInsider] = useState<InsiderTransaction[] | null>(null);

  useEffect(() => {
    fetchUWStatus()
      .then((s) => setFinnhubConfigured(s.configured))
      .catch(() => setFinnhubConfigured(false));
  }, []);

  const stocks = data?.stocks || {};
  const crypto = data?.crypto || {};
  const fx = data?.fx || {};
  const metals = data?.metals || {};
  const indices = data?.indices || {};
  const oil = data?.oil || {};
  const uw = data?.unusual_whales;
  const congressTrades = localCongress ?? uw?.congress_trades ?? [];
  const insiderTxns = localInsider ?? uw?.insider_transactions ?? [];

  const hasAnyMarketData = [stocks, crypto, fx, metals, indices, oil].some(
    (group) => Object.keys(group).length > 0,
  );

  const handleRefresh = useCallback(async () => {
    if (refreshing) return;
    setRefreshing(true);
    try {
      const [c, ins] = await Promise.all([
        fetchCongressTrades().catch(() => null),
        fetchInsiderTransactions().catch(() => null),
      ]);
      if (c?.trades) setLocalCongress(c.trades);
      if (ins?.transactions) setLocalInsider(ins.transactions);
    } finally {
      setRefreshing(false);
    }
  }, [refreshing]);

  return (
    <motion.div
      initial={{ y: -50, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.8, delay: 0.2 }}
      className="w-full bg-[#0a0a0a]/90 backdrop-blur-sm border border-cyan-900/40 z-10 flex flex-col font-mono text-sm pointer-events-auto flex-shrink-0"
    >
      <div
        className="flex justify-between items-center p-4 cursor-pointer hover:bg-[var(--bg-secondary)]/50 transition-colors border-b border-[var(--border-primary)]/50"
        onClick={() => {
          const next = !isMinimized;
          setIsMinimized(next);
          onFocusChange?.(!next);
        }}
      >
        <div className="flex items-center gap-2 min-w-0">
          <TrendingUp size={12} className="text-cyan-500" />
          <span className="text-[12px] text-[var(--text-muted)] font-mono tracking-widest truncate">CANLI KÜRESEL PİYASALAR</span>
          {data.financial_source && (
            <span className="text-[8px] text-green-500 bg-green-900/30 px-1 rounded uppercase truncate max-w-24">
              {data.financial_source}
            </span>
          )}
        </div>
        <button className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors" aria-label="Piyasa panelini aç/kapat">
          {isMinimized ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
        </button>
      </div>

      <AnimatePresence>
        {!isMinimized && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className={`overflow-y-auto styled-scrollbar flex flex-col ${focused ? 'max-h-[calc(100vh-180px)]' : 'max-h-[500px]'}`}
          >
            <div className="flex overflow-x-auto border-b border-[var(--border-primary)]/50 styled-scrollbar">
              {TAB_CONFIG.map((tab) => (
                <button
                  key={tab.key}
                  onClick={(event) => {
                    event.stopPropagation();
                    setActiveTab(tab.key);
                  }}
                  className={`shrink-0 min-w-[64px] flex items-center justify-center gap-1 px-2 py-2 text-[9px] tracking-wider transition-colors ${
                    activeTab === tab.key
                      ? 'text-cyan-400 border-b border-cyan-400 bg-cyan-950/20'
                      : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'
                  }`}
                >
                  {tab.icon}
                  {tab.label}
                </button>
              ))}
            </div>

            {(activeTab === 'congress' || activeTab === 'insider') && (
              <div className="flex justify-end px-3 pt-2 pb-1">
                <button
                  onClick={(event) => {
                    event.stopPropagation();
                    void handleRefresh();
                  }}
                  disabled={refreshing}
                  className="flex items-center gap-1 text-[9px] text-[var(--text-muted)] hover:text-cyan-400 transition-colors disabled:opacity-40"
                >
                  <RefreshCw size={10} className={refreshing ? 'animate-spin' : ''} />
                  {refreshing ? 'YENİLENİYOR...' : 'YENİLE'}
                </button>
              </div>
            )}

            <div className="p-3 flex flex-col gap-3">
              {activeTab === 'overview' && (
                hasAnyMarketData ? (
                  <>
                    <QuoteSection title="KÜRESEL ENDEKSLER" quotes={indices} />
                    <QuoteSection title="ENERJİ" quotes={oil} />
                    <QuoteSection title="TEKNOLOJİ / SAVUNMA" quotes={stocks} />
                  </>
                ) : <EmptyMarketState />
              )}
              {activeTab === 'fx' && (Object.keys(fx).length ? <QuoteSection title="DÖVİZ KURLARI" quotes={fx} priceMode="plain" /> : <EmptyMarketState />)}
              {activeTab === 'metals' && (Object.keys(metals).length ? <QuoteSection title="DEĞERLİ / STRATEJİK MADENLER" quotes={metals} /> : <EmptyMarketState />)}
              {activeTab === 'crypto' && (Object.keys(crypto).length ? <QuoteSection title="KRİPTO VARLIKLAR" quotes={crypto} /> : <EmptyMarketState />)}
              {activeTab === 'congress' && <CongressTab trades={congressTrades} />}
              {activeTab === 'insider' && <InsiderTab transactions={insiderTxns} />}
            </div>

            <div className="px-3 pb-3 border-t border-[var(--border-primary)]/30 pt-2">
              <p className="text-[8px] text-[var(--text-muted)]/70 text-center leading-relaxed">
                Piyasa kaynağı: {data.financial_source || 'bekleniyor'} · Fiyatlar kaynak sağlayıcının gecikmesine tabidir.
              </p>
              {data.financial_updated_at && (
                <p className="text-[8px] text-[var(--text-muted)]/50 text-center mt-1">
                  Son güncelleme: {new Date(data.financial_updated_at).toLocaleString('tr-TR')}
                </p>
              )}
              {finnhubConfigured === false && (activeTab === 'congress' || activeTab === 'insider') && (
                <div className="flex flex-col items-center gap-2 mt-2">
                  <div className="flex items-center gap-1.5">
                    <Settings size={10} className="text-[var(--text-muted)]" />
                    <p className="text-[9px] text-[var(--text-muted)]">
                      Kongre/içeriden işlem verisi için <span className="text-cyan-400">FINNHUB_API_KEY</span> ekleyin.
                    </p>
                  </div>
                  <a
                    href="https://finnhub.io/register"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-[11px] text-cyan-400 hover:text-cyan-300 transition-colors"
                  >
                    API anahtarı sayfası <ExternalLink size={8} />
                  </a>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
});

export default MarketsPanel;
