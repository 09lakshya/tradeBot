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

  const totalUnrealized = positions.reduce((a, p) => a + Number(p.unrealized_pnl ?? 0), 0);
  const totalRealized = positions.reduce((a, p) => a + Number(p.realized_pnl ?? 0), 0);

  const columns: Column<any>[] = [
    { key: "symbol", header: "Symbol", render: (r) => <span className="font-bold text-slate-100">{r.symbol}</span> },
    { key: "quantity", header: "Total Qty", align: "right", render: (r) => Number(r.quantity ?? 0).toLocaleString("en-IN") },
    { key: "avg_price", header: "FIFO Buy Cost", align: "right", render: (r) => formatINR(Number(r.average_buy_price ?? 0)) },
    { key: "current_price", header: "Mark-to-Market (LTP)", align: "right", render: (r) => formatINR(Number(r.current_price ?? 0)) },
    { key: "market_value", header: "Market Value (₹)", align: "right", render: (r) => formatINR(Number(r.quantity ?? 0) * Number(r.current_price ?? 0)) },
    {
      key: "unrealized_pnl",
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
        <MetricCard
          title="Total Open Positions"
          value={positions.length.toString()}
          subtext={positions.length === 1 ? "1 active symbol" : `${positions.length} active symbols`}
          accentColor="emerald"
        />
        <MetricCard title="Unrealized P&L" value={formatINR(totalUnrealized)} accentColor="cyan" />
        <MetricCard title="Realized P&L (EOD)" value={formatINR(totalRealized)} accentColor="purple" />
      </div>

      <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4">
        <h3 className="text-sm font-bold font-mono text-slate-100">Active Position Lots</h3>
        <DataTable
          columns={columns}
          data={
            positions
          }
          keyExtractor={(r, idx) => r.symbol || idx.toString()}
        />
      </div>
    </div>
  );
}
