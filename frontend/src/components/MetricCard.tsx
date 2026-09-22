"use client";

import React, { ReactNode } from "react";
import { TrendingUp, TrendingDown, HelpCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface MetricCardProps {
  title: string;
  value: string | number;
  subValue?: string;
  change?: number;
  changeLabel?: string;
  icon?: ReactNode;
  tooltip?: string;
  badge?: string;
  badgeType?: "neutral" | "success" | "warning" | "danger" | "cyan";
  highlight?: boolean;
}

export function MetricCard({
  title,
  value,
  subValue,
  change,
  changeLabel,
  icon,
  tooltip,
  badge,
  badgeType = "neutral",
  highlight = false,
}: MetricCardProps) {
  const isPositive = change !== undefined && change >= 0;
  const isNegative = change !== undefined && change < 0;

  const badgeStyles = {
    neutral: "bg-slate-800/80 text-slate-300 border-slate-700",
    success: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    warning: "bg-amber-500/10 text-amber-400 border-amber-500/20",
    danger: "bg-rose-500/10 text-rose-400 border-rose-500/20",
    cyan: "bg-cyan-500/10 text-cyan-400 border-cyan-500/20",
  };

  return (
    <div
      className={cn(
        "relative group p-4 rounded-xl transition-all duration-200 border bg-[#111827]/70  hover:border-slate-700/80 hover:shadow-lg hover:shadow-black/20",
        highlight ? "border-emerald-500/30 bg-gradient-to-br from-[#111827] via-[#111827] to-emerald-950/20" : "border-[#1e293b]"
      )}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
            {title}
          </span>
          {tooltip && (
            <div className="relative group/tooltip">
              <HelpCircle className="w-3.5 h-3.5 text-slate-500 hover:text-slate-300 cursor-help transition-colors" />
              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover/tooltip:block w-48 p-2 text-[11px] font-sans font-normal text-slate-200 bg-[#0f172a] rounded-lg border border-slate-700 shadow-xl z-50 pointer-events-none">
                {tooltip}
              </div>
            </div>
          )}
        </div>

        {badge && (
          <span className={cn("text-[10px] font-mono px-2 py-0.5 rounded border uppercase font-medium", badgeStyles[badgeType])}>
            {badge}
          </span>
        )}

        {icon && <div className="text-slate-400 group-hover:text-emerald-400 transition-colors">{icon}</div>}
      </div>

      {/* Primary Value */}
      <div className="flex items-baseline justify-between gap-2">
        <div className="text-2xl font-bold font-mono tracking-tight text-slate-100 group-hover:text-white transition-colors">
          {value}
        </div>

        {change !== undefined && (
          <div
            className={cn(
              "flex items-center text-xs font-mono font-semibold px-2 py-0.5 rounded-md",
              isPositive ? "text-emerald-400 bg-emerald-500/10" : "text-rose-400 bg-rose-500/10"
            )}
          >
            {isPositive ? <TrendingUp className="w-3 h-3 mr-1" /> : <TrendingDown className="w-3 h-3 mr-1" />}
            {isPositive ? "+" : ""}
            {change.toFixed(2)}%
          </div>
        )}
      </div>

      {/* Sub Value or Change Label */}
      {(subValue || changeLabel) && (
        <div className="mt-1.5 flex items-center justify-between text-xs text-slate-400 font-mono">
          {subValue && <span>{subValue}</span>}
          {changeLabel && <span className="text-slate-500">{changeLabel}</span>}
        </div>
      )}
    </div>
  );
}
