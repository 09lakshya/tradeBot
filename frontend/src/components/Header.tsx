"use client";

import React, { useState, useEffect } from "react";
import {
  Activity,
  Play,
  Pause,
  Square,
  RefreshCw,
  Clock,
  ShieldCheck,
  ChevronDown,
  Globe,
  Radio,
  Zap,
} from "lucide-react";
import { PortfolioAccount, SchedulerStatus, TradingDayInfo } from "@/lib/types";
import { controlScheduler } from "@/lib/api";

interface HeaderProps {
  portfolios: PortfolioAccount[];
  selectedPortfolioId: string;
  onSelectPortfolio: (id: string) => void;
  schedulerStatus: SchedulerStatus | null;
  onRefreshScheduler: () => void;
  nseStatus: TradingDayInfo | null;
  bseStatus: TradingDayInfo | null;
  autoRefresh: boolean;
  onToggleAutoRefresh: (val: boolean) => void;
  onManualRefresh: () => void;
  isRefreshing: boolean;
}

export function Header({
  portfolios,
  selectedPortfolioId,
  onSelectPortfolio,
  schedulerStatus,
  onRefreshScheduler,
  nseStatus,
  bseStatus,
  autoRefresh,
  onToggleAutoRefresh,
  onManualRefresh,
  isRefreshing,
}: HeaderProps) {
  const [time, setTime] = useState<string>("");

  useEffect(() => {
    const updateClock = () => {
      const now = new Date();
      setTime(
        now.toLocaleTimeString("en-IN", {
          hour12: false,
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          timeZone: "Asia/Kolkata",
        }) + " IST"
      );
    };
    updateClock();
    const interval = setInterval(updateClock, 1000);
    return () => clearInterval(interval);
  }, []);

  const handleSchedulerClick = async (action: "start" | "stop" | "pause" | "resume") => {
    await controlScheduler(action);
    onRefreshScheduler();
  };

  const selectedPortfolio = portfolios.find((p) => p.id === selectedPortfolioId) || portfolios[0];

  return (
    <header className="sticky top-0 z-50 bg-[#0a0e17]/90 backdrop-blur-md border-b border-[#1e293b] px-4 lg:px-8 py-3">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        {/* Left: Brand logo & Title */}
        <div className="flex items-center space-x-3">
          <div className="relative flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500/20 to-cyan-500/20 border border-emerald-500/30 text-emerald-400 shadow-lg shadow-emerald-500/10">
            <Zap className="w-5 h-5 animate-pulse" />
            <span className="absolute -top-1 -right-1 flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
            </span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold tracking-tight text-slate-100">
                TRADE BOT <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-mono">INSTITUTIONAL</span>
              </h1>
            </div>
            <p className="text-xs text-slate-400 font-mono flex items-center gap-1.5">
              <span>Autonomous Quantitative Execution</span>
              <span>•</span>
              <span className="text-cyan-400 font-semibold">{selectedPortfolio?.mode.toUpperCase()}</span>
            </p>
          </div>
        </div>

        {/* Center: Market Status & Live Clock */}
        <div className="flex flex-wrap items-center gap-2 lg:gap-4 bg-[#111827]/80 px-3.5 py-1.5 rounded-xl border border-[#1e293b]">
          {/* Live Clock */}
          <div className="flex items-center gap-1.5 text-xs text-slate-300 font-mono pr-3 border-r border-[#1e293b]">
            <Clock className="w-3.5 h-3.5 text-cyan-400" />
            <span>{time || "15:00:00 IST"}</span>
          </div>

          {/* NSE Status */}
          <div className="flex items-center gap-1.5 text-xs">
            <span className="font-semibold text-slate-300 font-mono">NSE:</span>
            {nseStatus?.is_trading_day ? (
              <span className="inline-flex items-center gap-1 text-emerald-400 font-mono px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                OPEN ({nseStatus.session_type})
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-rose-400 font-mono px-2 py-0.5 rounded bg-rose-500/10 border border-rose-500/20">
                <span className="w-1.5 h-1.5 rounded-full bg-rose-400"></span>
                CLOSED
              </span>
            )}
          </div>

          {/* BSE Status */}
          <div className="flex items-center gap-1.5 text-xs">
            <span className="font-semibold text-slate-300 font-mono">BSE:</span>
            {bseStatus?.is_trading_day ? (
              <span className="inline-flex items-center gap-1 text-emerald-400 font-mono px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                OPEN ({bseStatus.session_type})
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-rose-400 font-mono px-2 py-0.5 rounded bg-rose-500/10 border border-rose-500/20">
                <span className="w-1.5 h-1.5 rounded-full bg-rose-400"></span>
                CLOSED
              </span>
            )}
          </div>
        </div>

        {/* Right: Scheduler Control, Portfolio Selector & Refresh */}
        <div className="flex items-center gap-3">
          {/* Autonomous Scheduler Status */}
          <div className="flex items-center gap-2 bg-[#111827] px-3 py-1.5 rounded-xl border border-[#1e293b]">
            <div className="flex items-center gap-1.5">
              <Radio className={`w-3.5 h-3.5 ${schedulerStatus?.is_running ? "text-emerald-400 animate-pulse" : "text-amber-400"}`} />
              <span className="text-xs font-mono font-medium text-slate-300">
                Scheduler:
              </span>
              <span
                className={`text-xs font-mono font-semibold px-2 py-0.5 rounded ${
                  schedulerStatus?.is_running && !schedulerStatus?.is_paused
                    ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                    : schedulerStatus?.is_paused
                    ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                    : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                }`}
              >
                {schedulerStatus?.is_running && !schedulerStatus?.is_paused
                  ? "ACTIVE"
                  : schedulerStatus?.is_paused
                  ? "PAUSED"
                  : "STOPPED"}
              </span>
            </div>

            <div className="flex items-center gap-1 ml-1 pl-2 border-l border-[#1e293b]">
              {schedulerStatus?.is_running && !schedulerStatus?.is_paused ? (
                <button
                  onClick={() => handleSchedulerClick("pause")}
                  title="Pause Scheduler"
                  className="p-1 text-slate-400 hover:text-amber-400 hover:bg-amber-500/10 rounded transition-colors"
                >
                  <Pause className="w-3.5 h-3.5" />
                </button>
              ) : schedulerStatus?.is_paused ? (
                <button
                  onClick={() => handleSchedulerClick("resume")}
                  title="Resume Scheduler"
                  className="p-1 text-slate-400 hover:text-emerald-400 hover:bg-emerald-500/10 rounded transition-colors"
                >
                  <Play className="w-3.5 h-3.5" />
                </button>
              ) : (
                <button
                  onClick={() => handleSchedulerClick("start")}
                  title="Start Scheduler"
                  className="p-1 text-slate-400 hover:text-emerald-400 hover:bg-emerald-500/10 rounded transition-colors"
                >
                  <Play className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>

          {/* Portfolio Selector */}
          <div className="relative">
            <select
              value={selectedPortfolioId}
              onChange={(e) => onSelectPortfolio(e.target.value)}
              className="appearance-none bg-[#111827] text-slate-200 text-xs font-mono font-medium py-2 pl-3 pr-8 rounded-xl border border-[#1e293b] focus:outline-none focus:border-emerald-500/50 cursor-pointer"
            >
              {portfolios.map((p) => (
                <option key={p.id} value={p.id} className="bg-[#111827] text-slate-200">
                  {p.name} ({p.base_currency})
                </option>
              ))}
            </select>
            <ChevronDown className="w-3.5 h-3.5 text-slate-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>

          {/* Auto Refresh Toggle & Refresh Action */}
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => onToggleAutoRefresh(!autoRefresh)}
              title={autoRefresh ? "Auto-refresh enabled (10s)" : "Auto-refresh disabled"}
              className={`px-2.5 py-2 text-xs font-mono rounded-xl border transition-all flex items-center gap-1.5 ${
                autoRefresh
                  ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                  : "bg-[#111827] border-[#1e293b] text-slate-400 hover:text-slate-200"
              }`}
            >
              <Activity className={`w-3.5 h-3.5 ${autoRefresh ? "animate-pulse" : ""}`} />
              <span className="hidden sm:inline">{autoRefresh ? "LIVE 10s" : "PAUSED"}</span>
            </button>

            <button
              onClick={onManualRefresh}
              disabled={isRefreshing}
              title="Manual Telemetry Refresh"
              className="p-2 bg-[#111827] border border-[#1e293b] text-slate-300 hover:text-emerald-400 hover:border-emerald-500/40 rounded-xl transition-all disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin text-emerald-400" : ""}`} />
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
