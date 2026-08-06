"use client";

import React, { useState } from "react";
import { Position } from "@/lib/types";
import { formatCurrency, formatPercent } from "@/lib/utils";
import { Search, Filter, ArrowUpRight, ArrowDownRight, Briefcase } from "lucide-react";

interface PositionsTableProps {
  positions: Position[];
}

export function PositionsTable({ positions }: PositionsTableProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [sideFilter, setSideFilter] = useState<"ALL" | "LONG" | "SHORT">("ALL");

  const filteredPositions = positions.filter((pos) => {
    const matchesSearch =
      pos.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
      pos.sector?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesSide = sideFilter === "ALL" || pos.side === sideFilter;
    return matchesSearch && matchesSide;
  });

  const totalUnrealizedPnl = positions.reduce((acc, p) => acc + p.unrealized_pnl, 0);

  return (
    <div className="rounded-xl border border-[#1e293b] bg-[#111827]/80 backdrop-blur-md p-5 shadow-xl">
      {/* Table Header Controls */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4 pb-4 border-b border-[#1e293b]">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <Briefcase className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
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

        {/* Total Unrealized P&L Pill */}
        <div className="flex items-center gap-3">
          <div className="text-right font-mono">
            <div className="text-[11px] text-slate-400 uppercase">Unrealized P&L</div>
            <div className={`text-sm font-bold ${totalUnrealizedPnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {formatCurrency(totalUnrealizedPnl)}
            </div>
          </div>

          {/* Search & Filters */}
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search symbol/sector..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-[#0a0e17] text-slate-200 text-xs font-mono py-1.5 pl-8 pr-3 rounded-lg border border-[#1e293b] focus:outline-none focus:border-emerald-500/50 w-44"
              />
            </div>

            <div className="flex items-center bg-[#0a0e17] rounded-lg border border-[#1e293b] p-0.5 text-xs font-mono">
              <button
                onClick={() => setSideFilter("ALL")}
                className={`px-2.5 py-1 rounded transition-colors ${
                  sideFilter === "ALL" ? "bg-slate-800 text-slate-100 font-semibold" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                ALL
              </button>
              <button
                onClick={() => setSideFilter("LONG")}
                className={`px-2.5 py-1 rounded transition-colors ${
                  sideFilter === "LONG" ? "bg-emerald-500/20 text-emerald-400 font-semibold" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                LONG
              </button>
              <button
                onClick={() => setSideFilter("SHORT")}
                className={`px-2.5 py-1 rounded transition-colors ${
                  sideFilter === "SHORT" ? "bg-rose-500/20 text-rose-400 font-semibold" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                SHORT
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Table Data View */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-[#1e293b] text-[11px] font-mono uppercase text-slate-400 bg-[#0a0e17]/50">
              <th className="py-2.5 px-3">Symbol / Sector</th>
              <th className="py-2.5 px-3">Side</th>
              <th className="py-2.5 px-3 text-right">Quantity</th>
              <th className="py-2.5 px-3 text-right">Avg Entry</th>
              <th className="py-2.5 px-3 text-right">Current Price</th>
              <th className="py-2.5 px-3 text-right">Market Value</th>
              <th className="py-2.5 px-3 text-right">Unrealized P&L</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1e293b]/60 text-xs font-mono">
            {filteredPositions.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-8 text-center text-slate-500">
                  No active open positions matching search filters.
                </td>
              </tr>
            ) : (
              filteredPositions.map((pos) => {
                const pnlPct = ((pos.current_price - pos.average_entry_price) / pos.average_entry_price) * 100 * (pos.side === "SHORT" ? -1 : 1);
                const isPositive = pos.unrealized_pnl >= 0;

                return (
                  <tr key={pos.id} className="hover:bg-slate-800/40 transition-colors group">
                    <td className="py-3 px-3">
                      <div className="font-bold text-slate-200 group-hover:text-emerald-400 transition-colors">
                        {pos.symbol}
                      </div>
                      <div className="text-[10px] text-slate-400">{pos.sector || "General Equity"}</div>
                    </td>
                    <td className="py-3 px-3">
                      <span
                        className={`inline-flex items-center gap-0.5 px-2 py-0.5 rounded text-[10px] font-bold ${
                          pos.side === "LONG"
                            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                            : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                        }`}
                      >
                        {pos.side === "LONG" ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                        {pos.side}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-right text-slate-200 font-semibold">{pos.quantity}</td>
                    <td className="py-3 px-3 text-right text-slate-300">{formatCurrency(pos.average_entry_price)}</td>
                    <td className="py-3 px-3 text-right text-slate-200 font-semibold">{formatCurrency(pos.current_price)}</td>
                    <td className="py-3 px-3 text-right text-slate-200">{formatCurrency(pos.market_value)}</td>
                    <td className="py-3 px-3 text-right font-bold">
                      <div className={isPositive ? "text-emerald-400" : "text-rose-400"}>
                        {isPositive ? "+" : ""}
                        {formatCurrency(pos.unrealized_pnl)}
                      </div>
                      <div className={`text-[10px] ${isPositive ? "text-emerald-500" : "text-rose-500"}`}>
                        {formatPercent(pnlPct)}
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
