"use client";

import React, { useState } from "react";
import { Scan, Search, Filter } from "lucide-react";
import { DataTable, Column } from "@/components/common/DataTable";
import { formatINR } from "@/lib/utils";

export default function MarketScannerPage() {
  const [sectorFilter, setSectorFilter] = useState<string>("ALL");

  // The scanner has no backend endpoint yet, so there are no results to show.
  // Previously this table rendered a fixed set of invented symbols and signals.
  const results: any[] = [];

  const columns: Column<any>[] = [
    { key: "symbol", header: "Symbol", render: (r) => <span className="font-bold text-slate-100">{r.symbol}</span> },
    { key: "sector", header: "Sector", render: (r) => r.sector },
    { key: "price", header: "LTP (₹)", align: "right", render: (r) => formatINR(r.price) },
    { key: "change", header: "24h Change", align: "right", render: (r) => <span className="text-emerald-400 font-bold">+{r.change}%</span> },
    { key: "volume", header: "Volume (Shares)", align: "right", render: (r) => r.volume.toLocaleString("en-IN") },
    { key: "rsi", header: "RSI (14)", align: "right", render: (r) => r.rsi },
    { key: "signal", header: "Scanner Signal", render: (r) => <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-bold border border-emerald-500/20 text-[10px]">{r.signal}</span> },
  ];

  return (
    <div className="space-y-6">
      <div className="pb-2 border-b border-slate-800">
        <h1 className="text-xl font-bold text-slate-100 font-mono tracking-tight flex items-center gap-2">
          <Scan className="w-5 h-5 text-emerald-400" /> Real-time NSE/BSE Market Scanner & Screener
        </h1>
        <p className="text-xs text-slate-400 font-mono">
          Multi-factor algorithmic screening across liquidity, momentum breakouts, and RSI thresholds
        </p>
      </div>

      <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold font-mono text-slate-100">Live Screener Candidates</h3>
          <select
            value={sectorFilter}
            onChange={(e) => setSectorFilter(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-xs font-mono text-slate-100 outline-none"
          >
            <option value="ALL">All Sectors</option>
            <option value="IT">Information Tech</option>
            <option value="ENERGY">Oil & Gas / Energy</option>
            <option value="FINANCE">Banking & Financials</option>
          </select>
        </div>

        <DataTable
          columns={columns}
          data={results}
          emptyText="Market scanner is not connected to a data source yet."
          keyExtractor={(r, idx) => r.symbol || idx.toString()}
        />
      </div>
    </div>
  );
}
