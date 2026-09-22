"use client";

import React, { useState } from "react";
import { Trade } from "@/lib/types";
import { formatCurrency, formatDate } from "@/lib/utils";
import { History, Info, ArrowUpRight, ArrowDownRight, CheckCircle2 } from "lucide-react";
import { AdvancedTable, ColumnDef, SavedFilter } from "@/components/common/AdvancedTable";

interface TradesTableProps {
  trades: Trade[];
}

export function TradesTable({ trades }: TradesTableProps) {
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);

  const totalRealizedPnl = trades.reduce((acc, t) => acc + t.realized_pnl, 0);

  const columns: ColumnDef<Trade>[] = [
    {
      key: "trade_id",
      header: "Trade ID / Time",
      accessor: (row) => row.trade_id,
      pinned: "left",
      cell: (_, trade) => (
        <div>
          <div className="font-bold text-slate-200">{trade.trade_id}</div>
          <div className="text-[10px] text-slate-400">{formatDate(trade.execution_time)}</div>
        </div>
      ),
    },
    {
      key: "strategy_id",
      header: "Strategy",
      accessor: (row) => row.strategy_id,
      cell: (val) => (
        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-cyan-300 border border-slate-700">
          {val}
        </span>
      ),
    },
    {
      key: "symbol",
      header: "Symbol",
      accessor: (row) => row.symbol,
      cell: (val) => <div className="font-bold text-slate-200">{val}</div>,
    },
    {
      key: "side",
      header: "Side",
      accessor: (row) => row.side,
      cell: (val) => (
        <span
          className={`inline-flex items-center gap-0.5 px-2 py-0.5 rounded text-[10px] font-bold ${
 val === "BUY"
              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
              : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
          }`}
        >
          {val === "BUY" ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
          {val}
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
      key: "entry_price",
      header: "Entry Price",
      accessor: (row) => row.entry_price,
      cell: (val) => <div className="text-right text-slate-300">{formatCurrency(val)}</div>,
    },
    {
      key: "realized_pnl",
      header: "Realized P&L",
      accessor: (row) => row.realized_pnl,
      pinned: "right",
      cell: (val) => {
        const isPositive = val >= 0;
        return (
          <div className="text-right font-bold">
            <span className={isPositive ? "text-emerald-400" : "text-rose-400"}>
              {isPositive ? "+" : ""}
              {formatCurrency(val)}
            </span>
          </div>
        );
      },
    },
    {
      key: "detail",
      header: "Detail",
      accessor: () => null,
      sortable: false,
      cell: (_, trade) => (
        <div className="text-center">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setSelectedTrade(trade);
            }}
            className="p-1 text-slate-400 hover:text-cyan-400 hover:bg-cyan-500/10 rounded transition-colors"
            title="View Trade Detail & Rationale"
          >
            <Info className="w-4 h-4" />
          </button>
        </div>
      ),
    },
  ];

  const savedFilters: SavedFilter[] = [
    { id: "buys", name: "BUY Fills", filterFn: (t) => t.side === "BUY" },
    { id: "sells", name: "SELL Fills", filterFn: (t) => t.side === "SELL" },
    { id: "winners", name: "Profitable Fills", filterFn: (t) => t.realized_pnl > 0 },
    { id: "losers", name: "Negative Fills", filterFn: (t) => t.realized_pnl < 0 },
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between bg-slate-900/90 border border-slate-800 p-3.5 rounded-xl ">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
            <History className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              Executed Trades & Order Fills
              <span className="text-xs font-mono font-medium px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
                {trades.length} Fills
              </span>
            </h3>
            <p className="text-xs text-slate-400 font-mono">
              Immutable order execution log, trade fill prices & strategy attribution
            </p>
          </div>
        </div>

        <div className="text-right font-mono">
          <div className="text-[11px] text-slate-400 uppercase">Today's Realized P&L</div>
          <div className={`text-sm font-bold ${totalRealizedPnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {formatCurrency(totalRealizedPnl)}
          </div>
        </div>
      </div>

      <AdvancedTable
        data={trades}
        columns={columns}
        keyExtractor={(t) => t.trade_id}
        title="Execution Log"
        savedFilters={savedFilters}
        onRowClick={(trade) => setSelectedTrade(trade)}
        emptyMessage="No executed trade fills recorded."
      />

      {/* Trade Detail Modal */}
      {selectedTrade && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div className="bg-[#0f172a] border border-[#334155] rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-700">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                <h4 className="text-base font-bold text-slate-100 font-mono">
                  Trade Detail — {selectedTrade.trade_id}
                </h4>
              </div>
              <button
                onClick={() => setSelectedTrade(null)}
                className="text-slate-400 hover:text-white text-sm font-bold"
              >
                ✕
              </button>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs font-mono bg-slate-900/60 p-3 rounded-xl border border-slate-800">
              <div>
                <span className="text-slate-500 block">Strategy ID:</span>
                <span className="text-cyan-300 font-semibold">{selectedTrade.strategy_id}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Instrument:</span>
                <span className="text-slate-200 font-semibold">{selectedTrade.symbol}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Execution Time:</span>
                <span className="text-slate-300">{formatDate(selectedTrade.execution_time)}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Side / Qty:</span>
                <span className="text-slate-200 font-semibold">{selectedTrade.side} {selectedTrade.quantity} shares</span>
              </div>
              <div>
                <span className="text-slate-500 block">Fill Price:</span>
                <span className="text-slate-200">{formatCurrency(selectedTrade.entry_price)}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Realized P&L:</span>
                <span className={`font-bold ${selectedTrade.realized_pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {formatCurrency(selectedTrade.realized_pnl)}
                </span>
              </div>
            </div>

            <div className="space-y-1 font-mono">
              <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider">
                Signal & Execution Rationale:
              </span>
              <p className="text-xs text-slate-300 bg-slate-950 p-3 rounded-xl border border-slate-800 leading-relaxed">
                {selectedTrade.reason || "Autonomous quantitative signal execution."}
              </p>
            </div>

            <div className="pt-2 text-right">
              <button
                onClick={() => setSelectedTrade(null)}
                className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-slate-950 text-xs font-bold font-mono rounded-xl transition-colors"
              >
                Close Explanation
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
