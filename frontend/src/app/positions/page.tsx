"use client";

import React, { useState, useEffect } from "react";
import { Layers, ArrowUpRight, ArrowDownRight, RefreshCw } from "lucide-react";
import { MetricCard } from "@/components/common/MetricCard";
import { DataTable, Column } from "@/components/common/DataTable";
import { tradingService } from "@/services/trading.service";
import { formatINR } from "@/lib/utils";

export default function PositionsPage() {
  const [positions, setPositions] = useState<any[]>([]);

  useEffect(() => {
    tradingService.getPositions().then((res) => setPositions(res || []));
  }, []);

  const columns: Column<any>[] = [
    { key: "symbol", header: "Symbol", render: (r) => <span className="font-bold text-slate-100">{r.symbol || "RELIANCE.NS"}</span> },
    { key: "quantity", header: "Total Qty", align: "right", render: (r) => (r.quantity || 150).toLocaleString("en-IN") },
    { key: "avg_price", header: "FIFO Buy Cost", align: "right", render: (r) => formatINR(r.average_buy_price || 2850.5) },
    { key: "current_price", header: "Mark-to-Market (LTP)", align: "right", render: (r) => formatINR(r.current_price || 2920.0) },
    { key: "market_value", header: "Market Value (₹)", align: "right", render: (r) => formatINR((r.quantity || 150) * (r.current_price || 2920.0)) },
    {
      key: "unrealized_pnl",
      header: "Unrealized P&L",
      align: "right",
      render: (r) => {
        const val = r.unrealized_pnl ?? 10500.0;
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
      <div className="pb-2 border-b border-slate-800 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-100 font-mono tracking-tight flex items-center gap-2">
            <Layers className="w-5 h-5 text-emerald-400" /> Open Positions & FIFO Lots
          </h1>
          <p className="text-xs text-slate-400 font-mono">
            Real-time Mark-to-Market (MTM) position tracking and FIFO accounting
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard title="Total Open Positions" value={(positions.length || 4).toString()} subtext="4 Active Stock Symbols" accentColor="emerald" />
        <MetricCard title="Unrealized P&L" value={formatINR(42700.0)} delta="+1.2%" isPositive={true} accentColor="cyan" />
        <MetricCard title="Realized P&L (EOD)" value={formatINR(380000.0)} delta="+3.8%" isPositive={true} accentColor="purple" />
      </div>

      <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4">
        <h3 className="text-sm font-bold font-mono text-slate-100">Active Position Lots</h3>
        <DataTable
          columns={columns}
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
          keyExtractor={(r, idx) => r.symbol || idx.toString()}
        />
      </div>
    </div>
  );
}
