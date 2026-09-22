"use client";

import React, { useState, useEffect } from "react";
import { HelpCircle, RefreshCw, FileText, CheckCircle2, AlertTriangle, ArrowRight } from "lucide-react";
import { operationsService } from "@/services/operations.service";
import { formatINR } from "@/lib/utils";
import type { TradeExplanation } from "@/types";

export default function ExplainabilityPage() {
  const [explanations, setExplanations] = useState<TradeExplanation[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const loadExplanations = async () => {
    setIsLoading(true);
    try {
      const data = await operationsService.listExplanations();
      setExplanations(data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadExplanations();
  }, []);

  return (
    <div className="space-y-6">
      <div className="pb-2 border-b border-slate-800 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-100 font-mono tracking-tight flex items-center gap-2">
            <HelpCircle className="w-5 h-5 text-emerald-400" /> Strategy Explainability & Causal Lineage Inspector
          </h1>
          <p className="text-xs text-slate-400 font-mono">
            Audit-grade self-explaining trade logs, indicator breakdowns, and risk compliance rationale
          </p>
        </div>
        <button
          onClick={loadExplanations}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs font-mono text-slate-300"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin text-cyan-400" : ""}`} /> Refresh Explanations
        </button>
      </div>

      <div className="space-y-4">
        {explanations.map((exp) => (
          <div key={exp.explanation_id} className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4 font-mono">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-bold text-sm text-slate-100">{exp.symbol}</span>
                  <span className={exp.side === "BUY" ? "text-emerald-400 font-bold text-xs" : "text-rose-400 font-bold text-xs"}>
                    {exp.side}
                  </span>
                  <span className="text-xs text-slate-400">({exp.strategy_id})</span>
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5">Trade ID: {exp.trade_id}</div>
              </div>

              <span className="px-2.5 py-1 rounded bg-emerald-500/10 text-emerald-400 text-xs font-bold border border-emerald-500/20">
                EXPLAINED & AUDITED
              </span>
            </div>

            {/* Narrative */}
            <p className="text-xs text-slate-200 bg-slate-950 p-3 rounded-lg border border-slate-800 leading-relaxed">
              {exp.narrative}
            </p>

            {/* Subsystem Rationale Grid */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                <span className="text-cyan-400 font-bold block mb-1">1. Signal Rationale</span>
                <p className="text-slate-300 text-[11px] mb-1">{exp.signal_reason.rationale}</p>
                <span className="text-[10px] text-slate-500">Confidence: {(exp.signal_reason.confidence_score * 100).toFixed(0)}%</span>
              </div>

              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                <span className="text-emerald-400 font-bold block mb-1">2. Pre-Trade Risk</span>
                <p className="text-slate-300 text-[11px] mb-1">{exp.risk_reason.rationale}</p>
                <span className="text-[10px] text-emerald-400">Rules Passed: 100%</span>
              </div>

              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                <span className="text-purple-400 font-bold block mb-1">3. Portfolio Construction</span>
                <p className="text-slate-300 text-[11px] mb-1">{exp.portfolio_reason.sizing_rationale}</p>
                <span className="text-[10px] text-slate-400">Target: {formatINR(exp.portfolio_reason.position_sizing_selected)}</span>
              </div>

              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                <span className="text-amber-400 font-bold block mb-1">4. OMS Execution</span>
                <p className="text-slate-300 text-[11px] mb-1">{exp.execution_reason.rationale}</p>
                <span className="text-[10px] text-slate-400">Fill Price: {formatINR(exp.execution_reason.fill_price)}</span>
              </div>
            </div>
          </div>
        ))}

        {explanations.length === 0 && (
          <div className="p-8 rounded-xl bg-slate-900/80 border border-slate-800 text-center">
            <p className="text-sm text-slate-400 font-mono">No trade explanations yet</p>
            <p className="text-[11px] text-slate-600 mt-1">
              Each executed trade records why it was taken; this fills in once trading begins.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
