"use client";

import React, { useState, useEffect } from "react";
import { Cpu, Activity, Play, Pause, RefreshCw, AlertTriangle } from "lucide-react";
import { HealthBadge } from "@/components/common/HealthBadge";
import { MetricCard } from "@/components/common/MetricCard";
import { operationsService } from "@/services/operations.service";
import type { StrategyHealthReport } from "@/types";

export default function StrategiesPage() {
  const [reports, setReports] = useState<StrategyHealthReport[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const loadHealth = async () => {
    setIsLoading(true);
    try {
      const data = await operationsService.listHealthReports();
      setReports(data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadHealth();
  }, []);

  return (
    <div className="space-y-6">
      <div className="pb-2 border-b border-slate-800 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-100 font-mono tracking-tight flex items-center gap-2">
            <Cpu className="w-5 h-5 text-emerald-400" /> Strategy Registry & Health Degradation Monitor
          </h1>
          <p className="text-xs text-slate-400 font-mono">
            Continuous statistical drift detection, win-rate degradation, and live parameter control
          </p>
        </div>
        <button
          onClick={loadHealth}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs font-mono text-slate-300"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin text-cyan-400" : ""}`} /> Refresh Health
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard title="Registered Quantitative Strategies" value="3" subtext="All nominal & active" accentColor="emerald" />
        <MetricCard title="Avg Portfolio Sharpe Ratio" value="2.45" delta="+0.15" isPositive={true} accentColor="cyan" />
        <MetricCard title="Strategy Health Status" value="100% HEALTHY" subtext="0 degraded strategies" accentColor="purple" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {(reports
        ).map((st) => (
          <div key={st.strategy_id} className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div>
                <h3 className="font-mono text-sm font-bold text-slate-100 uppercase">{st.strategy_id}</h3>
                <span className="text-[11px] font-mono text-slate-400">Pure Signal Generator</span>
              </div>
              <HealthBadge status={st.is_degraded ? "degraded" : "nominal"} />
            </div>

            <div className="space-y-2 text-xs font-mono">
              <div className="flex justify-between">
                <span className="text-slate-400">Win Rate:</span>
                <span className="text-emerald-400 font-bold">{(st.win_rate * 100).toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Profit Factor:</span>
                <span className="text-slate-200 font-bold">{st.profit_factor.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Sharpe Ratio:</span>
                <span className="text-cyan-400 font-bold">{st.sharpe_ratio.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Current Drawdown:</span>
                <span className="text-amber-400 font-bold">{(st.current_drawdown * 100).toFixed(2)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">30D Net P&L:</span>
                <span className="text-emerald-400 font-bold">₹{st.recent_pnl_30d.toLocaleString("en-IN")}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
