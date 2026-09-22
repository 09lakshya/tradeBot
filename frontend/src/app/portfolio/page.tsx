"use client";

import React, { useState, useEffect } from "react";
import { Briefcase, PieChart, DollarSign, ArrowUpRight, ShieldCheck, Plus } from "lucide-react";
import { AddMoneyDialog } from "@/components/portfolio/AddMoneyDialog";
import { MetricCard } from "@/components/common/MetricCard";
import { DataTable, Column } from "@/components/common/DataTable";
import { operationsService } from "@/services/operations.service";
import { tradingService } from "@/services/trading.service";
import { formatINR, formatPercent } from "@/lib/utils";

export default function PortfolioPage() {
  const [snapshots, setSnapshots] = useState<any[]>([]);
  const [positions, setPositions] = useState<any[]>([]);
  const [portfolio, setPortfolio] = useState<any | null>(null);
  const [showAddMoney, setShowAddMoney] = useState(false);

  const loadData = () => {
    Promise.allSettled([
      operationsService.listSnapshots(undefined, undefined, 30),
      tradingService.getPositions(),
      tradingService.listPortfolios(),
    ]).then(([snapRes, posRes, portRes]) => {
      if (snapRes.status === "fulfilled") setSnapshots(snapRes.value.snapshots || []);
      if (posRes.status === "fulfilled") setPositions(posRes.value || []);
      if (portRes.status === "fulfilled") setPortfolio(portRes.value?.[0] ?? null);
    });
  };

  useEffect(loadData, []);

  const latestSnap = snapshots.length > 0 ? snapshots[snapshots.length - 1] : null;

  // Cash is read from the wallet itself. Daily snapshots are written by the EOD
  // job, so a deposit made today would not appear in one until that job runs.
  const cash = Number(portfolio?.cash_balance ?? 0);
  const invested = positions.reduce(
    (a, p) => a + Number(p.quantity ?? 0) * Number(p.average_buy_price ?? 0),
    0
  );
  const equity = invested + cash;

  const columns: Column<any>[] = [
    { key: "symbol", header: "Asset Symbol", render: (r) => <span className="font-bold">{r.symbol}</span> },
    { key: "sector", header: "Sector", render: (r) => r.sector ?? "—" },
    { key: "qty", header: "Quantity", align: "right", render: (r) => Number(r.quantity ?? 0).toLocaleString("en-IN") },
    { key: "avgPrice", header: "Avg Cost", align: "right", render: (r) => formatINR(Number(r.average_buy_price ?? 0)) },
    { key: "mktPrice", header: "Market Price", align: "right", render: (r) => formatINR(Number(r.current_price ?? 0)) },
    { key: "value", header: "Total Value", align: "right", render: (r) => formatINR(Number(r.quantity ?? 0) * Number(r.current_price ?? 0)) },
    {
      key: "pnl",
      header: "Unrealized P&L",
      align: "right",
      render: (r) => {
        const val = Number(r.unrealized_pnl ?? 0);
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
      <div className="pb-2 border-b border-slate-800">
        <h1 className="text-xl font-bold text-slate-100 font-mono tracking-tight flex items-center gap-2">
          <Briefcase className="w-5 h-5 text-emerald-400" /> Portfolio Analytics & Asset Allocation
        </h1>
        <div className="flex items-start justify-between gap-4">
          <p className="text-xs text-slate-400 font-mono">
            Detailed asset breakdown, cash reserves, and sector exposure in ₹ (INR)
          </p>
          <button
            onClick={() => setShowAddMoney(true)}
            className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-bold font-mono"
          >
            <Plus className="w-3.5 h-3.5" />
            {portfolio ? "Add Money" : "Add Money"}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Invested Capital"
          value={formatINR(invested)}
          subtext={equity > 0 ? `${((invested / equity) * 100).toFixed(1)}% portfolio allocation` : "Nothing allocated"}
          accentColor="emerald"
        />
        <MetricCard
          title="Unallocated Cash"
          value={formatINR(cash)}
          subtext={equity > 0 ? `${((cash / equity) * 100).toFixed(1)}% liquid cash reserves` : "Wallet not funded — use Add Money"}
          accentColor="cyan"
        />
        <MetricCard title="Total Realized P&L" value={formatINR(Number(latestSnap?.realized_pnl ?? 0))} accentColor="purple" />
        <MetricCard
          title="Cumulative Transaction Fees"
          value={formatINR(Number(latestSnap?.total_fees ?? 0))}
          subtext="STT, Brokerage & Exchange Fees"
          accentColor="amber"
        />
      </div>

      <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4">
        <h3 className="text-sm font-bold font-mono text-slate-100">Asset Holdings & Position Weights</h3>
        <DataTable
          columns={columns}
          data={
            positions
          }
          keyExtractor={(r, idx) => r.symbol || idx.toString()}
        />
      </div>

      {showAddMoney && (
        <AddMoneyDialog
          portfolioId={portfolio?.id ?? null}
          currentBalance={cash}
          onClose={() => setShowAddMoney(false)}
          onFunded={loadData}
        />
      )}
    </div>
  );
}
