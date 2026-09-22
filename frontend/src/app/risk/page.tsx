"use client";

import React, { useState, useEffect } from "react";
import { ShieldAlert, ShieldCheck, Power, AlertOctagon, RefreshCw } from "lucide-react";
import { MetricCard } from "@/components/common/MetricCard";
import { HealthBadge } from "@/components/common/HealthBadge";
import { riskService } from "@/services/risk.service";
import { formatINR, formatPercent } from "@/lib/utils";

export default function RiskPage() {
  const [killSwitchEngaged, setKillSwitchEngaged] = useState<boolean>(false);
  const [circuitBreakers, setCircuitBreakers] = useState<any[]>([]);

  const loadRiskData = async () => {
    try {
      const [ks, cb] = await Promise.allSettled([
        riskService.getKillSwitchStatus(),
        riskService.getCircuitBreakers(),
      ]);
      if (ks.status === "fulfilled") setKillSwitchEngaged(ks.value.is_engaged);
      if (cb.status === "fulfilled") setCircuitBreakers(cb.value || []);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadRiskData();
  }, []);

  const toggleKillSwitch = async () => {
    try {
      if (killSwitchEngaged) {
        await riskService.disengageKillSwitch();
      } else {
        await riskService.engageKillSwitch("Manual operator override from Risk Dashboard");
      }
      await loadRiskData();
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="space-y-6">
      <div className="pb-2 border-b border-slate-800 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-100 font-mono tracking-tight flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-rose-500" /> Pre-Trade Risk Engine & Kill Switch
          </h1>
          <p className="text-xs text-slate-400 font-mono">
            Institutional hard risk limits, circuit breakers, VaR constraints, and emergency shutdown
          </p>
        </div>

        <button
          onClick={loadRiskData}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs font-mono text-slate-300"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Refresh Risk State
        </button>
      </div>

      {/* Emergency Kill Switch Banner */}
      <div
        className={`p-5 rounded-xl border flex items-center justify-between transition-colors ${
          killSwitchEngaged
            ? "bg-rose-950/80 border-rose-500 text-rose-100 glow-rose"
            : "bg-slate-900/80 border-slate-800 text-slate-200"
        }`}
      >
        <div className="flex items-center gap-3">
          <AlertOctagon className={`w-8 h-8 ${killSwitchEngaged ? "text-rose-500 animate-pulse" : "text-emerald-400"}`} />
          <div>
            <h3 className="font-mono text-base font-bold">
              MASTER RISK KILL SWITCH: {killSwitchEngaged ? "ENGAGED (TRADING HALTED)" : "DISENGAGED (NOMINAL)"}
            </h3>
            <p className="text-xs font-mono text-slate-400">
              {killSwitchEngaged
                ? "All order routing suspended immediately. Outstanding limit orders cancelled."
                : "All pre-trade risk checks passing nominal threshold parameters."}
            </p>
          </div>
        </div>

        <button
          onClick={toggleKillSwitch}
          className={`px-4 py-2 rounded-lg font-mono font-bold text-xs flex items-center gap-2 transition-all ${
            killSwitchEngaged
              ? "bg-emerald-500 hover:bg-emerald-400 text-slate-950 shadow-lg"
              : "bg-rose-600 hover:bg-rose-500 text-white shadow-lg"
          }`}
        >
          <Power className="w-4 h-4" />
          {killSwitchEngaged ? "DISENGAGE KILL SWITCH" : "ENGAGE KILL SWITCH"}
        </button>
      </div>

      {/* Risk Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard title="Value at Risk (VaR 95%)" value={formatINR(0)} subtext="No exposure" accentColor="rose" />
        <MetricCard title="Current Drawdown" value={formatPercent(0)} subtext="Max Limit: 10.0%" accentColor="amber" />
        <MetricCard title="Gross Leverage" value="0.00x" subtext="Max Limit: 1.50x" accentColor="emerald" />
        <MetricCard title="Max Symbol Concentration" value="0.0%" subtext="Limit: 30.0%" accentColor="cyan" />
      </div>

      {/* Circuit Breakers Panel */}
      <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4">
        <h3 className="text-sm font-bold font-mono text-slate-100 flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-emerald-400" /> Active System Circuit Breakers
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 font-mono text-xs">
          {(circuitBreakers
          ).map((cb, idx) => (
            <div key={idx} className="p-3.5 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-between">
              <div>
                <span className="font-bold text-slate-200 uppercase">{cb.name || cb.breaker_id}</span>
                <div className="text-[11px] text-slate-400 mt-0.5">Failures: {cb.failure_count || 0}</div>
              </div>
              <HealthBadge status={cb.state === "closed" ? "healthy" : "critical"} label={cb.state === "closed" ? "CLOSED (NORMAL)" : "OPEN (TRIPPED)"} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
