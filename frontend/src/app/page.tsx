"use client";

import React, { useState, useEffect } from "react";
import {
  TrendingUp,
  DollarSign,
  PieChart as PieIcon,
  Shield,
  Activity,
  RefreshCw,
} from "lucide-react";
import { MetricCard } from "@/components/common/MetricCard";
import { HealthBadge } from "@/components/common/HealthBadge";
import { PositionsTable } from "@/components/PositionsTable";
import { TradesTable } from "@/components/TradesTable";
import { EnhancedTradingViewChart } from "@/components/charts/EnhancedTradingViewChart";
import { WorkspaceManager } from "@/components/workspace/WorkspaceManager";
import { ResizableGrid } from "@/components/workspace/ResizableGrid";
import { operationsService } from "@/services/operations.service";
import { tradingService } from "@/services/trading.service";
import { formatINR, formatPercent } from "@/lib/utils";
import type { DashboardReplayResponse, PortfolioDailySnapshot, StrategyHealthReport } from "@/types";

export default function DashboardPage() {
  const [dashboardData, setDashboardData] = useState<DashboardReplayResponse | null>(null);
  const [snapshots, setSnapshots] = useState<PortfolioDailySnapshot[]>([]);
  const [healthReports, setHealthReports] = useState<StrategyHealthReport[]>([]);
  const [positions, setPositions] = useState<any[]>([]);
  const [trades, setTrades] = useState<any[]>([]);
  const [portfolio, setPortfolio] = useState<any | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [dash, snapRes, hReports, posRes, tradeRes, portRes] = await Promise.allSettled([
        operationsService.getDashboardReplay(30),
        operationsService.listSnapshots(undefined, undefined, 30),
        operationsService.listHealthReports(),
        tradingService.getPositions(),
        tradingService.getTrades(),
        tradingService.listPortfolios(),
      ]);

      if (dash.status === "fulfilled") setDashboardData(dash.value);
      if (snapRes.status === "fulfilled") setSnapshots(snapRes.value.snapshots || []);
      if (hReports.status === "fulfilled") setHealthReports(hReports.value);
      if (posRes.status === "fulfilled") setPositions(posRes.value);
      if (tradeRes.status === "fulfilled") setTrades(tradeRes.value);
      if (portRes.status === "fulfilled") setPortfolio(portRes.value?.[0] ?? null);
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

  // Equity is the wallet's cash plus what is currently invested. The daily
  // snapshot is written by the EOD job, so it lags a deposit made today.
  const cash = Number(portfolio?.cash_balance ?? 0);
  const investedValue = positions.reduce(
    (a, p) => a + Number(p.quantity ?? 0) * Number(p.current_price ?? p.average_buy_price ?? 0),
    0
  );
  const totalEquity = cash + investedValue;

  // Derived from real fills only; with no trades there is nothing to average.
  const wins = trades.filter((t) => Number(t.realized_pnl) > 0).length;
  const losses = trades.filter((t) => Number(t.realized_pnl) < 0).length;
  const grossWin = trades.reduce((a, t) => a + Math.max(Number(t.realized_pnl) || 0, 0), 0);
  const grossLoss = trades.reduce((a, t) => a + Math.min(Number(t.realized_pnl) || 0, 0), 0);
  const winRate = wins + losses > 0 ? (wins / (wins + losses)) * 100 : 0;
  const profitFactor = grossLoss !== 0 ? grossWin / Math.abs(grossLoss) : 0;
  const winRateLabel = `${winRate.toFixed(1)}% / ${profitFactor.toFixed(2)}`;

  const renderWidgetContent = (widgetId: string) => {
    switch (widgetId) {
      case "chart":
        return <EnhancedTradingViewChart height={360} />;
      case "metrics":
        return (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <MetricCard
              title="Total Portfolio Equity"
              value={formatINR(totalEquity)}
              subtext={portfolio ? `Cash ${formatINR(cash)} · marked to market` : "No wallet yet — add money on Portfolio"}
              icon={TrendingUp}
              accentColor="emerald"
            />
            <MetricCard
              title="Today's P&L"
              value={formatINR(latestSnap?.unrealized_pnl ?? 0)}
              subtext="Net of fees & slippage"
              icon={DollarSign}
              accentColor="cyan"
            />
            <MetricCard
              title="Win Rate / Profit Factor"
              value={trades.length > 0 ? winRateLabel : "—"}
              subtext={trades.length > 0 ? "Last 30 trading days" : "No trades yet"}
              icon={PieIcon}
              accentColor="purple"
            />
            <MetricCard
              title="Max Drawdown"
              value={formatPercent(latestSnap?.drawdown ?? 0)}
              subtext="Risk Limit: 10.0%"
              icon={Shield}
              accentColor="amber"
            />
          </div>
        );
      case "positions":
        return <PositionsTable positions={positions} />;
      case "trades":
        return <TradesTable trades={trades} />;
      default:
        return null;
    }
  };

  return (
    <div className="space-y-4">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-800">
        <div>
          <h1 className="text-xl font-bold text-slate-100 font-mono tracking-tight flex items-center gap-2">
            Institutional Quantitative Dashboard{" "}
            <span className="text-xs px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-normal border border-emerald-500/20">
              AUTONOMOUS MODE
            </span>
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

      {/* Workspace System Bar */}
      <WorkspaceManager />

      {/* Resizable Dynamic Widget Grid */}
      <ResizableGrid renderWidget={renderWidgetContent} />
    </div>
  );
}
