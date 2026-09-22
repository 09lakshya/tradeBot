"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Activity, Pause, Play, RefreshCw, Radio } from "lucide-react";
import { MetricCard } from "@/components/common/MetricCard";
import { DataTable, Column } from "@/components/common/DataTable";
import { apiFetch } from "@/services/client";
import { formatINR } from "@/lib/utils";

const POLL_MS = 15000;

interface CycleOutcome {
  timestamp: string;
  ran: boolean;
  reason: string;
  signals: number;
  candidates: number;
  approved: number;
  rejected: number;
  submitted: number;
  filled: number;
  duration_ms: number;
  error: string | null;
}

interface TraderStatus {
  running: boolean;
  enabled_by_config: boolean;
  market_session: string;
  market_open: boolean;
  interval_seconds: number;
  strategies: number;
  symbol_limit: number;
  cycles_attempted: number;
  cycles_executed: number;
  last_cycle: CycleOutcome | null;
  recent: CycleOutcome[];
}

interface Trade {
  order_id: string;
  symbol: string;
  name: string;
  side: string;
  status: string;
  quantity: string;
  filled_quantity: string;
  avg_fill_price: string | null;
  stop_price: string | null;
  notional: string;
  total_charges: string;
  strategies: string[];
  confidence: string | null;
  risk_reward: string | null;
  reason: string | null;
  created_at: string | null;
}

interface TradeFeed {
  count: number;
  strategy_usage: Record<string, number>;
  trades: Trade[];
}

export default function LiveTradingPage() {
  const [status, setStatus] = useState<TraderStatus | null>(null);
  const [feed, setFeed] = useState<TradeFeed | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const load = useCallback(async () => {
    const [s, f] = await Promise.allSettled([
      apiFetch<TraderStatus>("/api/v1/orchestrator/autotrader/status"),
      apiFetch<TradeFeed>("/api/v1/orchestrator/autotrader/trades?limit=100"),
    ]);
    if (s.status === "fulfilled") setStatus(s.value);
    if (f.status === "fulfilled") setFeed(f.value);
    setLastRefresh(new Date());
  }, []);

  useEffect(() => {
    load();
    if (!autoRefresh) return;
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load, autoRefresh]);

  const sessionTone = status?.market_open
    ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/40"
    : "bg-slate-700/40 text-slate-400 border-slate-700";

  const columns: Column<Trade>[] = [
    {
      key: "created_at",
      header: "Time",
      render: (r) =>
        r.created_at
          ? new Date(r.created_at).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" })
          : "—",
    },
    {
      key: "symbol",
      header: "Symbol",
      render: (r) => <span className="font-bold text-slate-100">{r.symbol}</span>,
    },
    {
      key: "side",
      header: "Side",
      render: (r) => (
        <span
          className={
            r.side === "buy" ? "text-emerald-400 font-bold uppercase" : "text-rose-400 font-bold uppercase"
          }
        >
          {r.side}
        </span>
      ),
    },
    { key: "quantity", header: "Qty", align: "right", render: (r) => Number(r.filled_quantity).toLocaleString("en-IN") },
    {
      key: "avg_fill_price",
      header: "Fill",
      align: "right",
      render: (r) => (r.avg_fill_price ? formatINR(Number(r.avg_fill_price)) : "—"),
    },
    { key: "notional", header: "Value", align: "right", render: (r) => formatINR(Number(r.notional)) },
    {
      key: "stop_price",
      header: "Stop",
      align: "right",
      render: (r) => (r.stop_price ? <span className="text-rose-300">{formatINR(Number(r.stop_price))}</span> : "—"),
    },
    {
      key: "strategies",
      header: "Strategies",
      render: (r) =>
        r.strategies.length ? (
          <div className="flex flex-wrap gap-1">
            {r.strategies.map((s) => (
              <span
                key={s}
                className="px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/30 text-[10px]"
              >
                {s}
              </span>
            ))}
          </div>
        ) : (
          <span className="text-slate-600">manual</span>
        ),
    },
    {
      key: "confidence",
      header: "Conf.",
      align: "right",
      render: (r) => (r.confidence ? `${(Number(r.confidence) * 100).toFixed(0)}%` : "—"),
    },
    {
      key: "detail",
      header: "Why",
      render: (r) => (
        <button
          onClick={() => setExpanded(expanded === r.order_id ? null : r.order_id)}
          className="text-[11px] text-emerald-400 hover:text-emerald-300 underline"
        >
          {expanded === r.order_id ? "hide" : "reason"}
        </button>
      ),
    },
  ];

  const usage = Object.entries(feed?.strategy_usage ?? {});
  const last = status?.last_cycle;

  return (
    <div className="space-y-6">
      <div className="pb-2 border-b border-slate-800 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-100 font-mono tracking-tight flex items-center gap-2">
            <Radio className={`w-5 h-5 ${status?.running ? "text-emerald-400 animate-pulse" : "text-slate-600"}`} />
            Live Trading
          </h1>
          <p className="text-xs text-slate-400 font-mono">
            Every order the autonomous trader places, and the strategies behind it
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-[11px] font-mono px-2 py-1 rounded border ${sessionTone}`}>
            NSE {status?.market_session ?? "…"}
          </span>
          <button
            onClick={() => setAutoRefresh((v) => !v)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs font-mono text-slate-300 hover:border-emerald-500"
          >
            {autoRefresh ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
            {autoRefresh ? "Auto" : "Paused"}
          </button>
          <button
            onClick={load}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs font-mono text-slate-300 hover:border-emerald-500"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Trader"
          value={status?.running ? "Running" : "Stopped"}
          subtext={
            status?.market_open
              ? `cycle every ${Math.round((status?.interval_seconds ?? 0) / 60)} min`
              : "idle until the market opens"
          }
          accentColor={status?.running ? "emerald" : "amber"}
        />
        <MetricCard
          title="Cycles Executed"
          value={String(status?.cycles_executed ?? 0)}
          subtext={`${status?.cycles_attempted ?? 0} attempted`}
          accentColor="cyan"
        />
        <MetricCard
          title="Orders Placed"
          value={String(feed?.count ?? 0)}
          subtext={last ? `last cycle: ${last.filled} filled of ${last.candidates}` : "no cycle yet"}
          accentColor="purple"
        />
        <MetricCard
          title="Strategies Loaded"
          value={String(status?.strategies ?? 0)}
          subtext={`watching ${status?.symbol_limit ?? 0} symbols`}
          accentColor="emerald"
        />
      </div>

      {last && (
        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 font-mono text-[11px] text-slate-400 flex flex-wrap items-center gap-x-5 gap-y-2">
          <span className="flex items-center gap-1.5 text-slate-200">
            <Activity className="w-3.5 h-3.5 text-emerald-400" />
            Last cycle
          </span>
          <span>{new Date(last.timestamp).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" })} IST</span>
          <span>status: <span className="text-slate-200">{last.reason}</span></span>
          <span>signals: <span className="text-slate-200">{last.signals}</span></span>
          <span>candidates: <span className="text-slate-200">{last.candidates}</span></span>
          <span>risk approved: <span className="text-emerald-400">{last.approved}</span></span>
          <span>rejected: <span className="text-rose-400">{last.rejected}</span></span>
          <span>filled: <span className="text-slate-200">{last.filled}</span></span>
          <span>{last.duration_ms.toFixed(0)} ms</span>
          {last.error && <span className="text-rose-400">error: {last.error}</span>}
        </div>
      )}

      {usage.length > 0 && (
        <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-3">
          <h3 className="text-sm font-bold font-mono text-slate-100">Strategies Driving Trades</h3>
          <div className="flex flex-wrap gap-2">
            {usage.map(([name, count]) => (
              <span
                key={name}
                className="px-2 py-1 rounded-lg bg-cyan-500/10 text-cyan-300 border border-cyan-500/30 text-[11px] font-mono"
              >
                {name} <span className="text-cyan-100 font-bold">×{count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold font-mono text-slate-100">Order Flow</h3>
          <span className="text-[10px] font-mono text-slate-500">
            {lastRefresh ? `updated ${lastRefresh.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" })}` : ""}
          </span>
        </div>
        <DataTable
          columns={columns}
          data={feed?.trades ?? []}
          keyExtractor={(r) => r.order_id}
          emptyText="No orders yet. The trader places its first orders after the market opens."
        />
        {expanded && (
          <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-[11px] font-mono text-slate-300">
            {feed?.trades.find((t) => t.order_id === expanded)?.reason ?? "No decision record."}
          </div>
        )}
      </div>
    </div>
  );
}
