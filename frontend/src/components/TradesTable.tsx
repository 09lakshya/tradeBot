"use client";

import React, { useState } from "react";
import { Trade } from "@/lib/types";
import { formatCurrency, formatDate } from "@/lib/utils";
import { History, Info, ArrowUpRight, ArrowDownRight, CheckCircle2 } from "lucide-react";

interface TradesTableProps {
  trades: Trade[];
}

export function TradesTable({ trades }: TradesTableProps) {
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);

  const totalRealizedPnl = trades.reduce((acc, t) => acc + t.realized_pnl, 0);

  return (
    <div className="rounded-xl border border-[#1e293b] bg-[#111827]/80 backdrop-blur-md p-5 shadow-xl">
      {/* Table Header Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4 pb-4 border-b border-[#1e293b]">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
            <History className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
              Today's Executed Trades & Order Fills
              <span className="text-xs font-mono font-medium px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
                {trades.length} Trades
              </span>
            </h3>
            <p className="text-xs text-slate-400 font-mono">
              Immutable ledger order fills, execution times & signal reasoning
            </p>
          </div>
        </div>

        {/* Realized P&L Total */}
        <div className="text-right font-mono">
          <div className="text-[11px] text-slate-400 uppercase">Today's Realized P&L</div>
          <div className={`text-sm font-bold ${totalRealizedPnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {formatCurrency(totalRealizedPnl)}
          </div>
        </div>
      </div>

      {/* Table Data View */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-[#1e293b] text-[11px] font-mono uppercase text-slate-400 bg-[#0a0e17]/50">
              <th className="py-2.5 px-3">Trade ID / Time</th>
              <th className="py-2.5 px-3">Strategy</th>
              <th className="py-2.5 px-3">Symbol</th>
              <th className="py-2.5 px-3">Side</th>
              <th className="py-2.5 px-3 text-right">Quantity</th>
              <th className="py-2.5 px-3 text-right">Entry Price</th>
              <th className="py-2.5 px-3 text-right">Realized P&L</th>
              <th className="py-2.5 px-3 text-center">Detail</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1e293b]/60 text-xs font-mono">
            {trades.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-8 text-center text-slate-500">
                  No trade executions recorded for today yet.
                </td>
              </tr>
            ) : (
              trades.map((trade) => {
                const isPositive = trade.realized_pnl >= 0;

                return (
                  <tr key={trade.trade_id} className="hover:bg-slate-800/40 transition-colors group">
                    <td className="py-3 px-3">
                      <div className="font-bold text-slate-200 font-mono">{trade.trade_id}</div>
                      <div className="text-[10px] text-slate-400">{formatDate(trade.execution_time)}</div>
                    </td>
                    <td className="py-3 px-3">
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-cyan-300 border border-slate-700">
                        {trade.strategy_id}
                      </span>
                    </td>
                    <td className="py-3 px-3 font-bold text-slate-200">{trade.symbol}</td>
                    <td className="py-3 px-3">
                      <span
                        className={`inline-flex items-center gap-0.5 px-2 py-0.5 rounded text-[10px] font-bold ${
                          trade.side === "BUY"
                            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                            : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                        }`}
                      >
                        {trade.side === "BUY" ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                        {trade.side}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-right text-slate-200 font-semibold">{trade.quantity}</td>
                    <td className="py-3 px-3 text-right text-slate-300">{formatCurrency(trade.entry_price)}</td>
                    <td className="py-3 px-3 text-right font-bold">
                      <span className={isPositive ? "text-emerald-400" : "text-rose-400"}>
                        {isPositive ? "+" : ""}
                        {formatCurrency(trade.realized_pnl)}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-center">
                      <button
                        onClick={() => setSelectedTrade(trade)}
                        className="p-1 text-slate-400 hover:text-cyan-400 hover:bg-cyan-500/10 rounded transition-colors"
                        title="View Trade Reasoning & Journal"
                      >
                        <Info className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

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
