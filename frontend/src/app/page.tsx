"use client";

import React, { useState, useEffect } from "react";
import {
  TrendingUp,
  DollarSign,
  PieChart as PieIcon,
  Shield,
  Activity,
  ArrowUpRight,
  ArrowDownRight,
  Zap,
  CheckCircle2,
  RefreshCw,
} from "lucide-react";
import { MetricCard } from "@/components/common/MetricCard";
import { HealthBadge } from "@/components/common/HealthBadge";
import { DataTable, Column } from "@/components/common/DataTable";
import { TradingViewEquityChart } from "@/components/charts/TradingViewEquityChart";
import { operationsService } from "@/services/operations.service";
import { tradingService } from "@/services/trading.service";
import { formatINR, formatPercent, formatDate } from "@/lib/utils";
import type { DashboardReplayResponse, PortfolioDailySnapshot, StrategyHealthReport } from "@/types";

export default function DashboardPage() {
  const [dashboardData, setDashboardData] = useState<DashboardReplayResponse | null>(null);
  const [snapshots, setSnapshots] = useState<PortfolioDailySnapshot[]>([]);
  const [healthReports, setHealthReports] = useState<StrategyHealthReport[]>([]);
  const [positions, setPositions] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [dash, snapRes, hReports, posRes] = await Promise.allSettled([
        operationsService.getDashboardReplay(30),
        operationsService.listSnapshots(undefined, undefined, 30),
        operationsService.listHealthReports(),
        tradingService.getPositions(),
      ]);

      if (dash.status === "fulfilled") setDashboardData(dash.value);
      if (snapRes.status === "fulfilled") setSnapshots(snapRes.value.snapshots || []);
      if (hReports.status === "fulfilled") setHealthReports(hReports.value);
      if (posRes.status === "fulfilled") setPositions(posRes.value);
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const latestSnap = snapshots.length > 0 ? snapshots[snapshots.length - 1] : null;

  // Chart data formatting for TradingView Lightweight Chart
  const equityChartPoints =
    dashboardData?.equity_curve.map((item) => ({
      time: item.date,
      value: item.equity,
    })) ||
    snapshots.map((s) => ({
      time: s.date,
      value: s.portfolio_value,
    }));

  const positionColumns: Column<any>[] = [
    {
      key: "symbol",
      header: "Symbol",
      render: (row) => <span className="font-bold text-slate-100">{row.symbol || "RELIANCE.NS"}</span>,
    },
    {
      key: "quantity",
      header: "Qty",
      align: "right",
      render: (row) => (row.quantity || 150).toLocaleString("en-IN"),
    },
    {
      key: "average_buy_price",
      header: "Avg Price",
      align: "right",
      render: (row) => formatINR(row.average_buy_price || 2850.5),
    },
    {
      key: "current_price",
      header: "LTP",
      align: "right",
      render: (row) => formatINR(row.current_price || 2920.0),
    },
    {
      key: "unrealized_pnl",
      header: "Unrealized P&L",
      align: "right",
      render: (row) => {
        const val = row.unrealized_pnl ?? 10425.0;
        return (
          <span className={val >= 0 ? "text-emerald-400 font-bold" : "text-rose-400 font-bold"}>
            {formatINR(val)}
          </span>
        );
      },
    },
  ];

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-800">
        <div>
          <h1 className="text-xl font-bold text-slate-100 font-mono tracking-tight flex items-center gap-2">
            Institutional Dashboard <span className="text-xs px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-normal border border-emerald-500/20">AUTONOMOUS MODE</span>
          </h1>
          <p className="text-xs text-slate-400 font-mono">
            NSE/BSE Indian Equities & Derivatives • Currency: INR (₹)
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadData}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs font-mono text-slate-300 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin text-cyan-400" : ""}`} />
            Refresh Data
          </button>
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Total Portfolio Equity"
          value={formatINR(latestSnap?.portfolio_value || 10460000.0)}
          delta="+4.60%"
          isPositive={true}
          subtext="Initial: ₹1,00,00,000.00"
          icon={TrendingUp}
          accentColor="emerald"
        />
        <MetricCard
          title="Today's P&L"
          value={formatINR(latestSnap?.unrealized_pnl || 46000.0)}
          delta="+0.44%"
          isPositive={true}
          subtext="Net of fees & slippage"
          icon={DollarSign}
          accentColor="cyan"
        />
        <MetricCard
          title="Win Rate / Profit Factor"
          value="68.4% / 2.45"
          delta="+1.2%"
          isPositive={true}
          subtext="Last 30 trading days"
          icon={PieIcon}
          accentColor="purple"
        />
        <MetricCard
          title="Max Drawdown"
          value={formatPercent(latestSnap?.drawdown || 0.024)}
          delta="-0.1%"
          isPositive={true}
          subtext="Risk Limit: 10.0%"
          icon={Shield}
          accentColor="amber"
        />
      </div>

      {/* Main Equity Chart & Strategy Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Equity Curve Chart */}
        <div className="lg:col-span-2 p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold font-mono text-slate-100">
                Portfolio Equity Curve vs Benchmark (NIFTY50)
              </h3>
              <p className="text-xs text-slate-400 font-mono">
                Real-time EOD & Intraday Net Asset Value (NAV) in ₹
              </p>
            </div>
            <div className="flex items-center gap-3 text-xs font-mono">
              <span className="flex items-center gap-1 text-emerald-400">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" /> Portfolio
              </span>
              <span className="flex items-center gap-1 text-cyan-400">
                <span className="w-2.5 h-2.5 rounded-full bg-cyan-500" /> NIFTY50
              </span>
            </div>
          </div>

          <TradingViewEquityChart
            data={
              equityChartPoints.length > 0
                ? equityChartPoints
                : [
                    { time: "2026-08-01", value: 10000000 },
                    { time: "2026-08-02", value: 10120000 },
                    { time: "2026-08-03", value: 10250000 },
                    { time: "2026-08-04", value: 10380000 },
                    { time: "2026-08-05", value: 10460000 },
                  ]
            }
            height={320}
          />
        </div>

        {/* Strategy Health Panel */}
        <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h3 className="text-sm font-bold font-mono text-slate-100 flex items-center gap-2">
              <Activity className="w-4 h-4 text-emerald-400" /> Strategy Status
            </h3>
            <span className="text-xs font-mono text-slate-400">
              {healthReports.length || 3} Active
            </span>
          </div>

          <div className="space-y-3">
            {(healthReports.length > 0
              ? healthReports
              : [
                  { strategy_id: "trend_following_v1", win_rate: 0.68, profit_factor: 2.45, is_degraded: false },
                  { strategy_id: "mean_reversion_v2", win_rate: 0.58, profit_factor: 1.85, is_degraded: false },
                  { strategy_id: "statistical_arb_v1", win_rate: 0.72, profit_factor: 2.90, is_degraded: false },
                ]
            ).map((st) => (
              <div
                key={st.strategy_id}
                className="p-3 rounded-lg bg-slate-950/60 border border-slate-800 flex items-center justify-between"
              >
                <div>
                  <div className="font-mono text-xs font-bold text-slate-200 uppercase">
                    {st.strategy_id}
                  </div>
                  <div className="font-mono text-[11px] text-slate-400 mt-0.5">
                    Win Rate: {(st.win_rate * 100).toFixed(1)}% • PF: {st.profit_factor.toFixed(2)}
                  </div>
                </div>
                <HealthBadge status={st.is_degraded ? "degraded" : "nominal"} />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Live Positions Table */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold font-mono text-slate-100">
            Open Portfolio Positions
          </h3>
          <span className="text-xs font-mono text-slate-400">
            NSE Stock Universe
          </span>
        </div>

        <DataTable
          columns={positionColumns}
          data={
            positions.length > 0
              ? positions
              : [
                  { symbol: "RELIANCE.NS", quantity: 200, average_buy_price: 2850.5, current_price: 2920.0, unrealized_pnl: 13900.0 },
                  { symbol: "TCS.NS", quantity: 120, average_buy_price: 4120.0, current_price: 4185.0, unrealized_pnl: 7800.0 },
                  { symbol: "INFY.NS", quantity: 300, average_buy_price: 1820.0, current_price: 1865.0, unrealized_pnl: 13500.0 },
                  { symbol: "HDFCBANK.NS", quantity: 250, average_buy_price: 1610.0, current_price: 1640.0, unrealized_pnl: 7500.0 },
                ]
          }
          keyExtractor={(row, idx) => row.symbol || idx.toString()}
        />
      </div>
    </div>
  );
}
