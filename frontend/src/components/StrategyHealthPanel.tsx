"use client";

import React from "react";
import { StrategyHealth } from "@/lib/types";
import { formatPercent } from "@/lib/utils";
import { Activity, ShieldCheck, AlertTriangle, ShieldAlert, Cpu } from "lucide-react";

interface StrategyHealthPanelProps {
  strategies: StrategyHealth[];
}

export function StrategyHealthPanel({ strategies }: StrategyHealthPanelProps) {
  return (
    <div className="rounded-xl border border-[#1e293b] bg-[#111827]/80 p-5 shadow-xl">
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-[#1e293b]">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <Cpu className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
              Strategy Health & Statistical Invariant Monitor
            </h3>
            <p className="text-xs text-slate-400 font-mono">
              Live quantitative risk controls, win rate, Sharpe ratios & degradation detection
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {strategies.map((strat) => {
          const isHealthy = strat.status === "HEALTHY" && !strat.degradation_detected;

          return (
            <div
              key={strat.strategy_id}
              className={`p-4 rounded-xl border transition-all ${
 isHealthy
                  ? "border-[#1e293b] bg-[#0a0e17]/60 hover:border-emerald-500/40"
                  : "border-rose-500/40 bg-rose-950/20"
              }`}
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h4 className="text-sm font-bold text-slate-100 font-mono flex items-center gap-1.5">
                    {strat.strategy_id}
                  </h4>
                  <span className="text-[10px] text-slate-400 font-mono">{strat.notes || "Quant Strategy"}</span>
                </div>

                <span
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase ${
 isHealthy
                      ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                      : "bg-rose-500/10 text-rose-400 border border-rose-500/20 animate-pulse"
                  }`}
                >
                  {isHealthy ? <ShieldCheck className="w-3 h-3" /> : <ShieldAlert className="w-3 h-3" />}
                  {strat.status}
                </span>
              </div>

              {/* Health Score Progress Bar */}
              <div className="mb-4">
                <div className="flex justify-between text-xs font-mono mb-1">
                  <span className="text-slate-400">Health Index:</span>
                  <span className={`font-bold ${strat.health_score >= 85 ? "text-emerald-400" : "text-amber-400"}`}>
                    {strat.health_score} / 100
                  </span>
                </div>
                <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all duration-500 rounded-full ${
 strat.health_score >= 85
                        ? "bg-gradient-to-r from-emerald-500 to-cyan-400"
                        : "bg-gradient-to-r from-amber-500 to-rose-500"
                    }`}
                    style={{ width: `${Math.min(100, Math.max(0, strat.health_score))}%` }}
                  ></div>
                </div>
              </div>

              {/* Key Metrics Grid */}
              <div className="grid grid-cols-3 gap-2 text-center text-xs font-mono bg-[#111827] p-2.5 rounded-lg border border-[#1e293b]">
                <div>
                  <span className="text-[10px] text-slate-400 block">Win Rate</span>
                  <span className="font-bold text-slate-200">{formatPercent(strat.win_rate * 100)}</span>
                </div>
                <div>
                  <span className="text-[10px] text-slate-400 block">Sharpe</span>
                  <span className="font-bold text-slate-200">{strat.sharpe_ratio.toFixed(2)}</span>
                </div>
                <div>
                  <span className="text-[10px] text-slate-400 block">Max DD</span>
                  <span className="font-bold text-rose-400">{(strat.max_drawdown * 100).toFixed(1)}%</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
