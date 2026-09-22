"use client";

import React from "react";
import { PieChart, Zap, CheckCircle2, ArrowRight } from "lucide-react";
import { DataTable, Column } from "@/components/common/DataTable";
import { formatINR } from "@/lib/utils";

export default function PortfolioConstructionPage() {
  const signalColumns: Column<any>[] = [
    { key: "symbol", header: "Symbol", render: (r) => <span className="font-bold">{r.symbol}</span> },
    { key: "strategy", header: "Source Strategy", render: (r) => <span className="text-cyan-400 font-mono">{r.strategy}</span> },
    { key: "signal", header: "Signal", render: (r) => <span className="text-emerald-400 font-bold">{r.signal}</span> },
    { key: "confidence", header: "Confidence", align: "right", render: (r) => `${(r.confidence * 100).toFixed(0)}%` },
    { key: "sizing", header: "Target Sizing (₹)", align: "right", render: (r) => formatINR(r.target_sizing) },
    { key: "status", header: "Arbitration", render: (r) => <span className="text-emerald-400 font-bold">APPROVED</span> },
  ];

  return (
    <div className="space-y-6">
      <div className="pb-2 border-b border-slate-800">
        <h1 className="text-xl font-bold text-slate-100 font-mono tracking-tight flex items-center gap-2">
          <PieChart className="w-5 h-5 text-emerald-400" /> Signal Arbitration & Portfolio Construction
        </h1>
        <p className="text-xs text-slate-400 font-mono">
          Multi-strategy signal aggregation, ranking, risk parity sizing, and candidate order generation
        </p>
      </div>

      <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4">
        <h3 className="text-sm font-bold font-mono text-slate-100 flex items-center gap-2">
          <Zap className="w-4 h-4 text-emerald-400" /> Active Candidate Signals for Arbitration
        </h3>
        <DataTable
          columns={signalColumns}
          data={[]}
          emptyText="No candidate signals — no strategy is running yet."
          keyExtractor={(r, idx) => r.symbol || idx.toString()}
        />
      </div>
    </div>
  );
}
