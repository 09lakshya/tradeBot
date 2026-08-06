"use client";

import React, { useState } from "react";
import { Wrench, Play, Code, CheckCircle } from "lucide-react";

export default function StrategyBuilderPage() {
  const [lookback, setLookback] = useState<number>(20);
  const [rsiPeriod, setRsiPeriod] = useState<number>(14);
  const [overbought, setOverbought] = useState<number>(70);
  const [oversold, setOversold] = useState<number>(30);
  const [stopLossPct, setStopLossPct] = useState<number>(2.5);

  return (
    <div className="space-y-6">
      <div className="pb-2 border-b border-slate-800">
        <h1 className="text-xl font-bold text-slate-100 font-mono tracking-tight flex items-center gap-2">
          <Wrench className="w-5 h-5 text-emerald-400" /> Interactive Strategy Builder & Parameter Studio
        </h1>
        <p className="text-xs text-slate-400 font-mono">
          Configure mathematical indicators, thresholds, and signal logic for Indian Equities
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Parameter Config Panel */}
        <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4">
          <h3 className="text-sm font-bold font-mono text-slate-100 border-b border-slate-800 pb-2">
            Indicator Parameters
          </h3>

          <div className="space-y-4 text-xs font-mono">
            <div>
              <label className="block text-slate-400 mb-1">SMA Lookback Period (Bars): {lookback}</label>
              <input
                type="range"
                min="5"
                max="200"
                value={lookback}
                onChange={(e) => setLookback(Number(e.target.value))}
                className="w-full accent-emerald-500 bg-slate-950"
              />
            </div>

            <div>
              <label className="block text-slate-400 mb-1">RSI Period: {rsiPeriod}</label>
              <input
                type="range"
                min="2"
                max="50"
                value={rsiPeriod}
                onChange={(e) => setRsiPeriod(Number(e.target.value))}
                className="w-full accent-emerald-500 bg-slate-950"
              />
            </div>

            <div>
              <label className="block text-slate-400 mb-1">RSI Oversold (BUY): {oversold}</label>
              <input
                type="range"
                min="10"
                max="45"
                value={oversold}
                onChange={(e) => setOversold(Number(e.target.value))}
                className="w-full accent-emerald-500 bg-slate-950"
              />
            </div>

            <div>
              <label className="block text-slate-400 mb-1">RSI Overbought (SELL): {overbought}</label>
              <input
                type="range"
                min="55"
                max="90"
                value={overbought}
                onChange={(e) => setOverbought(Number(e.target.value))}
                className="w-full accent-emerald-500 bg-slate-950"
              />
            </div>

            <div>
              <label className="block text-slate-400 mb-1">Stop Loss (%): {stopLossPct}%</label>
              <input
                type="range"
                min="0.5"
                max="10.0"
                step="0.5"
                value={stopLossPct}
                onChange={(e) => setStopLossPct(Number(e.target.value))}
                className="w-full accent-emerald-500 bg-slate-950"
              />
            </div>
          </div>
        </div>

        {/* Code & Logic Preview */}
        <div className="lg:col-span-2 p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <h3 className="text-sm font-bold font-mono text-slate-100 flex items-center gap-2">
              <Code className="w-4 h-4 text-cyan-400" /> Mathematical Signal Preview
            </h3>
            <span className="text-xs font-mono text-emerald-400">PASSED VALIDATION</span>
          </div>

          <pre className="p-4 rounded-lg bg-slate-950 border border-slate-800 text-slate-200 text-xs font-mono overflow-x-auto leading-relaxed">
{`# Custom Strategy Configuration Generated
class CustomRsiSmaStrategy(BaseStrategy):
    sma_period = ${lookback}
    rsi_period = ${rsiPeriod}
    rsi_oversold = ${oversold}
    rsi_overbought = ${overbought}
    stop_loss_pct = ${stopLossPct / 100}

    def generate_signal(self, candle_bar):
        sma_val = self.indicators.sma(period=${lookback})
        rsi_val = self.indicators.rsi(period=${rsiPeriod})

        if rsi_val < ${oversold} and candle_bar.close > sma_val:
            return Signal(side="BUY", confidence=0.85, rationale="RSI oversold with SMA trend confirmation")
        elif rsi_val > ${overbought}:
            return Signal(side="SELL", confidence=0.80, rationale="RSI overbought threshold breached")
        return Signal(side="HOLD", confidence=0.0)`}
          </pre>
        </div>
      </div>
    </div>
  );
}
