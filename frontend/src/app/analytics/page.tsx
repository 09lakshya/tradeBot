"use client";

import React from "react";
import { LineChart, BarChart, TrendingUp } from "lucide-react";
import { MetricCard } from "@/components/common/MetricCard";
import { TradingViewEquityChart } from "@/components/charts/TradingViewEquityChart";

export default function AnalyticsPage() {
  return (
    <div className="space-y-6">
      <div className="pb-2 border-b border-slate-800">
        <h1 className="text-xl font-bold text-slate-100 font-mono tracking-tight flex items-center gap-2">
          <LineChart className="w-5 h-5 text-emerald-400" /> Institutional Quantitative Analytics
        </h1>
        <p className="text-xs text-slate-400 font-mono">
          Rolling risk-adjusted return metrics, drawdown distributions, and factor attribution
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard title="Rolling 30D Sharpe Ratio" value="2.68" delta="+0.12" isPositive={true} accentColor="emerald" />
        <MetricCard title="Sortino Ratio (Downside Risk)" value="3.42" delta="+0.18" isPositive={true} accentColor="cyan" />
        <MetricCard title="Calmar Ratio" value="5.89" accentColor="purple" />
        <MetricCard title="Beta vs NIFTY50" value="0.48" subtext="Low market correlation" accentColor="amber" />
      </div>

      <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4">
        <h3 className="text-sm font-bold font-mono text-slate-100">Rolling 30-Day Sharpe Ratio Evolution</h3>
        <TradingViewEquityChart
          data={[
            { time: "2026-08-01", value: 2.45 },
            { time: "2026-08-02", value: 2.52 },
            { time: "2026-08-03", value: 2.58 },
            { time: "2026-08-04", value: 2.62 },
            { time: "2026-08-05", value: 2.68 },
          ]}
          height={280}
        />
      </div>
    </div>
  );
}
