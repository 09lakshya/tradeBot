"use client";

import React, { useState } from "react";
import { History, Play, BarChart2, TrendingUp } from "lucide-react";
import { MetricCard } from "@/components/common/MetricCard";
import { TradingViewEquityChart } from "@/components/charts/TradingViewEquityChart";
import { formatINR, formatPercent } from "@/lib/utils";

export default function BacktestingPage() {
  const [strategy, setStrategy] = useState<string>("trend_following_v1");
  const [symbol, setSymbol] = useState<string>("RELIANCE.NS");
  const [startDate, setStartDate] = useState<string>("2024-01-01");
  const [endDate, setEndDate] = useState<string>("2026-08-01");
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [hasRun, setHasRun] = useState<boolean>(false);

  // The backtest API (/api/v1/backtest) exists but is not wired to this screen yet.
  // This used to fake a 1.5s "simulation" and then display fixed, invented results.
  const handleRunBacktest = (e: React.FormEvent) => {
    e.preventDefault();
    setHasRun(true);
  };

  return (
    <div className="space-y-6">
      <div className="pb-2 border-b border-slate-800">
        <h1 className="text-xl font-bold text-slate-100 font-mono tracking-tight flex items-center gap-2">
          <History className="w-5 h-5 text-emerald-400" /> Backtesting Engine, Monte Carlo & Walk-Forward Studio
        </h1>
        <p className="text-xs text-slate-400 font-mono">
          Event-driven point-in-time historical simulation with purged cross-validation
        </p>
      </div>

      {/* Form Setup */}
      <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800">
        <form onSubmit={handleRunBacktest} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 text-xs font-mono">
          <div>
            <label className="block text-slate-400 mb-1">Strategy</label>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-slate-100 outline-none"
            >
              <option value="trend_following_v1">Trend Following v1</option>
              <option value="mean_reversion_v2">Mean Reversion v2</option>
              <option value="statistical_arb_v1">Statistical Arb v1</option>
            </select>
          </div>

          <div>
            <label className="block text-slate-400 mb-1">Stock Ticker</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-slate-100 outline-none"
            />
          </div>

          <div>
            <label className="block text-slate-400 mb-1">Start Date</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-slate-100 outline-none"
            />
          </div>

          <div>
            <label className="block text-slate-400 mb-1">End Date</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-slate-100 outline-none"
            />
          </div>

          <div className="flex items-end">
            <button
              type="submit"
              disabled={isRunning}
              className="w-full py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
            >
              <Play className="w-3.5 h-3.5" />
              {isRunning ? "Simulating..." : "Execute Backtest"}
            </button>
          </div>
        </form>
      </div>

      {/* Results */}
      {hasRun && (
        <div className="p-8 rounded-xl bg-slate-900/80 border border-slate-800 text-center">
          <p className="text-sm text-slate-300 font-mono">Backtest engine not connected to this screen</p>
          <p className="text-[11px] text-slate-500 mt-1">
            The backend exposes /api/v1/backtest, but this page has no client for it yet.
            No simulated results are shown rather than placeholder numbers.
          </p>
        </div>
      )}

    </div>
  );
}
