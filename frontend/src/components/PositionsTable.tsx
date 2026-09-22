"use client";

import React from "react";
import { Position } from "@/lib/types";
import { formatCurrency, formatPercent } from "@/lib/utils";
import { ArrowUpRight, ArrowDownRight, Briefcase } from "lucide-react";
import { AdvancedTable, ColumnDef, SavedFilter } from "@/components/common/AdvancedTable";

interface PositionsTableProps {
  positions: Position[];
}

export function PositionsTable({ positions }: PositionsTableProps) {
  const totalUnrealizedPnl = positions.reduce((acc, p) => acc + p.unrealized_pnl, 0);

  const columns: ColumnDef<Position>[] = [
    {
      key: "symbol",
      header: "Symbol / Sector",
      accessor: (row) => row.symbol,
      pinned: "left",
      cell: (_, pos) => (
        <div>
          <div className="font-bold text-slate-200">{pos.symbol}</div>
          <div className="text-[10px] text-slate-400">{pos.sector || "General Equity"}</div>
        </div>
      ),
    },
    {
      key: "side",
      header: "Side",
      accessor: (row) => row.side,
      cell: (side) => (
        <span
          className={`inline-flex items-center gap-0.5 px-2 py-0.5 rounded text-[10px] font-bold ${
 side === "LONG"
              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
              : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
          }`}
        >
          {side === "LONG" ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
          {side}
        </span>
      ),
    },
    {
      key: "quantity",
      header: "Quantity",
      accessor: (row) => row.quantity,
      cell: (val) => <div className="text-right text-slate-200 font-semibold">{val}</div>,
    },
    {
      key: "average_entry_price",
      header: "Avg Entry",
      accessor: (row) => row.average_entry_price,
      cell: (val) => <div className="text-right text-slate-300">{formatCurrency(val)}</div>,
    },
    {
      key: "current_price",
      header: "Current Price",
      accessor: (row) => row.current_price,
      cell: (val) => <div className="text-right text-slate-200 font-semibold">{formatCurrency(val)}</div>,
    },
    {
      key: "market_value",
      header: "Market Value",
      accessor: (row) => row.market_value,
      cell: (val) => <div className="text-right text-slate-200">{formatCurrency(val)}</div>,
    },
    {
      key: "unrealized_pnl",
      header: "Unrealized P&L",
      accessor: (row) => row.unrealized_pnl,
      pinned: "right",
      cell: (val, pos) => {
        const pnlPct = ((pos.current_price - pos.average_entry_price) / pos.average_entry_price) * 100 * (pos.side === "SHORT" ? -1 : 1);
        const isPositive = val >= 0;
        return (
          <div className="text-right font-bold">
            <div className={isPositive ? "text-emerald-400" : "text-rose-400"}>
              {isPositive ? "+" : ""}
              {formatCurrency(val)}
            </div>
            <div className={`text-[10px] ${isPositive ? "text-emerald-500" : "text-rose-500"}`}>
              {formatPercent(pnlPct)}
            </div>
          </div>
        );
      },
    },
  ];

  const savedFilters: SavedFilter[] = [
    { id: "longs", name: "LONG Only", filterFn: (pos) => pos.side === "LONG" },
    { id: "shorts", name: "SHORT Only", filterFn: (pos) => pos.side === "SHORT" },
    { id: "profitable", name: "Profitable", filterFn: (pos) => pos.unrealized_pnl > 0 },
    { id: "lossmaking", name: "In Loss", filterFn: (pos) => pos.unrealized_pnl < 0 },
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between bg-slate-900/90 border border-slate-800 p-3.5 rounded-xl ">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <Briefcase className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              Active Portfolio Positions
              <span className="text-xs font-mono font-medium px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
                {positions.length} Open
              </span>
            </h3>
            <p className="text-xs text-slate-400 font-mono">
              Live unrealized mark-to-market valuations and positions inventory
            </p>
          </div>
        </div>

        <div className="text-right font-mono">
          <div className="text-[11px] text-slate-400 uppercase">Unrealized P&L</div>
          <div className={`text-sm font-bold ${totalUnrealizedPnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {formatCurrency(totalUnrealizedPnl)}
          </div>
        </div>
      </div>

      <AdvancedTable
        data={positions}
        columns={columns}
        keyExtractor={(p) => p.id}
        title="Positions Inventory"
        savedFilters={savedFilters}
        emptyMessage="No active open positions matching criteria."
      />
    </div>
  );
}
