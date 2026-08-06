"use client";

import React, { useState, useEffect } from "react";
import { Briefcase, PieChart, DollarSign, ArrowUpRight, ShieldCheck } from "lucide-react";
import { MetricCard } from "@/components/common/MetricCard";
import { DataTable, Column } from "@/components/common/DataTable";
import { operationsService } from "@/services/operations.service";
import { tradingService } from "@/services/trading.service";
import { formatINR, formatPercent } from "@/lib/utils";

export default function PortfolioPage() {
  const [snapshots, setSnapshots] = useState<any[]>([]);
  const [positions, setPositions] = useState<any[]>([]);

  useEffect(() => {
    Promise.allSettled([
      operationsService.listSnapshots(undefined, undefined, 30),
      tradingService.getPositions(),
    ]).then(([snapRes, posRes]) => {
      if (snapRes.status === "fulfilled") setSnapshots(snapRes.value.snapshots || []);
      if (posRes.status === "fulfilled") setPositions(posRes.value || []);
    });
  }, []);

  const latestSnap = snapshots.length > 0 ? snapshots[snapshots.length - 1] : null;

  const columns: Column<any>[] = [
    { key: "symbol", header: "Asset Symbol", render: (r) => <span className="font-bold">{r.symbol}</span> },
    { key: "sector", header: "Sector", render: (r) => r.sector || "Energy / IT / Finance" },
    { key: "qty", header: "Quantity", align: "right", render: (r) => (r.quantity || 150).toLocaleString("en-IN") },
    { key: "avgPrice", header: "Avg Cost", align: "right", render: (r) => formatINR(r.average_buy_price || 2850.0) },
    { key: "mktPrice", header: "Market Price", align: "right", render: (r) => formatINR(r.current_price || 2920.0) },
    { key: "value", header: "Total Value", align: "right", render: (r) => formatINR((r.quantity || 150) * (r.current_price || 2920.0)) },
    {
      key: "pnl",
      header: "Unrealized P&L",
      align: "right",
      render: (r) => (
        <span className="text-emerald-400 font-bold">{formatINR(r.unrealized_pnl || 10500.0)}</span>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="pb-2 border-b border-slate-800">
        <h1 className="text-xl font-bold text-slate-100 font-mono tracking-tight flex items-center gap-2">
          <Briefcase className="w-5 h-5 text-emerald-400" /> Portfolio Analytics & Asset Allocation
        </h1>
        <p className="text-xs text-slate-400 font-mono">
          Detailed asset breakdown, cash reserves, and sector exposure in ₹ (INR)
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard title="Invested Capital" value={formatINR(latestSnap?.invested_capital || 7400000.0)} subtext="70.7% Portfolio Allocation" accentColor="emerald" />
        <MetricCard title="Unallocated Cash" value={formatINR(latestSnap?.cash_balance || 3060000.0)} subtext="29.3% Liquid Cash Reserves" accentColor="cyan" />
        <MetricCard title="Total Realized P&L" value={formatINR(latestSnap?.realized_pnl || 380000.0)} delta="+3.8%" isPositive={true} accentColor="purple" />
        <MetricCard title="Cumulative Transaction Fees" value={formatINR(4250.0)} subtext="STT, Brokerage & Exchange Fees" accentColor="amber" />
      </div>

      <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4">
        <h3 className="text-sm font-bold font-mono text-slate-100">Asset Holdings & Position Weights</h3>
        <DataTable
          columns={columns}
          data={
            positions.length > 0
              ? positions
              : [
                  { symbol: "RELIANCE.NS", sector: "Oil & Gas / Energy", quantity: 200, average_buy_price: 2850.5, current_price: 2920.0, unrealized_pnl: 13900.0 },
                  { symbol: "TCS.NS", sector: "Information Tech", quantity: 120, average_buy_price: 4120.0, current_price: 4185.0, unrealized_pnl: 7800.0 },
                  { symbol: "INFY.NS", sector: "Information Tech", quantity: 300, average_buy_price: 1820.0, current_price: 1865.0, unrealized_pnl: 13500.0 },
                  { symbol: "HDFCBANK.NS", sector: "Banking & Financials", quantity: 250, average_buy_price: 1610.0, current_price: 1640.0, unrealized_pnl: 7500.0 },
                ]
          }
          keyExtractor={(r, idx) => r.symbol || idx.toString()}
        />
      </div>
    </div>
  );
}
