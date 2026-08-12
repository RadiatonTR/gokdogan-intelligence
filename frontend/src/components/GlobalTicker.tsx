'use client';

import { useState } from 'react';
import { motion } from '@/lib/motion';
import { ArrowUpRight, ArrowDownRight, TrendingUp, AlertTriangle, ChevronUp, CircleCheck } from 'lucide-react';
import { useDataKeys } from '@/hooks/useDataStore';

export default function GlobalTicker() {
  const { stocks, crypto, fx, metals, indices, oil, financial_source } = useDataKeys(['stocks', 'crypto', 'fx', 'metals', 'indices', 'oil', 'financial_source'] as const);
  const entries = Object.entries({ ...(indices || {}), ...(fx || {}), ...(metals || {}), ...(crypto || {}), ...(oil || {}), ...(stocks || {}) });
  const fallback = financial_source === 'yfinance';

  if (entries.length === 0) return null;

  // Render a single ticker item
  const renderItem = ([ticker, info]: [string, any], index: number) => {
    // Determine color based on price action
    let colorClass = 'text-white';
    if (info.change_percent > 0) colorClass = 'text-green-400';
    if (info.change_percent < 0) colorClass = 'text-red-400';

    const isCryptoHighlight = ticker === 'BTC' || ticker === 'ETH';

    return (
      <div 
        key={`${ticker}-${index}`} 
        className={`flex items-center gap-3 shrink-0 mx-5 font-mono ${isCryptoHighlight ? 'bg-cyan-950/30 px-3 py-1 rounded-sm border border-cyan-500/20 shadow-[0_0_10px_rgba(6,182,212,0.15)]' : ''}`}
      >
        <span className={`font-bold text-[11px] uppercase tracking-widest ${isCryptoHighlight ? 'text-cyan-400' : 'text-cyan-300'}`}>
          {isCryptoHighlight && <span className="mr-1.5 text-cyan-500">★</span>}
          {ticker}
        </span>
        <span className={`font-bold text-[12px] ${isCryptoHighlight ? 'text-white' : 'text-[var(--text-primary)]'}`}>
          {(info.price ?? 0).toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
        <span className={`flex items-center gap-0.5 text-[10px] font-bold ${colorClass}`}>
          {info.up ? <ArrowUpRight size={12} /> : info.change_percent < 0 ? <ArrowDownRight size={12} /> : <span className="w-3"></span>}
          {Math.abs(info.change_percent ?? 0).toFixed(2)}%
        </span>
      </div>
    );
  };


  return (
    <div
      className="absolute bottom-0 left-0 right-0 h-7 bg-[#0a0a0a]/95 border-t border-cyan-900/40 shadow-[0_-5px_15px_rgba(0,0,0,0.6)] z-[8000] flex items-center overflow-hidden pointer-events-auto backdrop-blur-xl"
    >

      {fallback && (
        <div className="absolute right-0 top-0 bottom-0 bg-gradient-to-l from-emerald-950/80 via-black/70 to-transparent w-[390px] z-10 flex items-center justify-end px-4 pointer-events-none">
          <div className="flex items-center gap-2 text-emerald-300 bg-emerald-950/35 px-2 pl-3 py-0.5 border border-emerald-500/20 rounded">
            <CircleCheck size={10} />
            <span className="text-[9px] font-mono font-bold tracking-wider uppercase">
              PİYASA VERİSİ: YAHOO FINANCE • FINNHUB İSTEĞE BAĞLI
            </span>
          </div>
        </div>
      )}

      {/* The scrolling container */}
      <motion.div
        className="flex items-center whitespace-nowrap will-change-transform pl-4"
        animate={{ x: ["0%", "-50%"] }}
        transition={{ ease: "linear", duration: 60, repeat: Infinity }}
      >
        {/* Render the list twice for seamless infinite scrolling */}
        <div className="flex items-center">
          {entries.map((item, i) => renderItem(item, i))}
        </div>
        <div className="flex items-center">
          {entries.map((item, i) => renderItem(item, i + entries.length))}
        </div>
      </motion.div>
    </div>
  );
}
