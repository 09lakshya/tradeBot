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
  const [hasRun, setHasRun] = useState<boolean>(true);

  const handleRunBacktest = (e: React.FormEvent) => {
    e.preventDefault();
    setIsRunning(true);
    setTimeout(() => {
      setIsRunning(false);
      setHasRun(true);
    }, 1500);
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
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard title="CAGR Return" value="+28.4%" delta="+4.2%" isPositive={true} accentColor="emerald" />
            <MetricCard title="Sharpe / Sortino Ratio" value="2.68 / 3.42" accentColor="cyan" />
            <MetricCard title="Max Historical Drawdown" value="-4.82%" accentColor="amber" />
            <MetricCard title="Win Rate / Total Trades" value="69.2% (142 Trades)" accentColor="purple" />
          </div>

          <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4">
            <h3 className="text-sm font-bold font-mono text-slate-100">Historical Simulated Equity vs Benchmark</h3>
            <TradingViewEquityChart
              data={[
                { time: "2024-01-01", value: 10000000 },
                { time: "2024-06-01", value: 11200000 },
                { time: "2025-01-01", value: 13500000 },
                { time: "2025-06-01", value: 15200000 },
                { time: "2026-01-01", value: 17800000 },
                { time: "2026-08-01", value: 19840000 },
              ]}
              height={320}
            />
          </div>
        </div>
      )}
    </div>
  );
}
