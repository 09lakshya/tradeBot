import React from "react";
import { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface MetricCardProps {
  title: string;
  value: string | number;
  delta?: string;
  isPositive?: boolean;
  subtext?: string;
  icon?: LucideIcon;
  accentColor?: "emerald" | "cyan" | "purple" | "amber" | "rose";
  className?: string;
}

export function MetricCard({
  title,
  value,
  delta,
  isPositive,
  subtext,
  icon: Icon,
  accentColor = "emerald",
  className,
}: MetricCardProps) {
  const accentBorderMap = {
    emerald: "hover:border-emerald-500/50",
    cyan: "hover:border-cyan-500/50",
    purple: "hover:border-purple-500/50",
    amber: "hover:border-amber-500/50",
    rose: "hover:border-rose-500/50",
  };

  return (
    <div
      className={cn(
        "p-4 rounded-xl bg-slate-900/80  border border-slate-800 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg",
        accentBorderMap[accentColor],
        className
      )}
    >
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs font-medium text-slate-400">{title}</span>
        {Icon && <Icon className="w-4 h-4 text-slate-500" />}
      </div>

      <div className="flex items-baseline justify-between">
        <h3 className="text-xl font-bold font-mono text-slate-100 tracking-tight">
          {value}
        </h3>
        {delta && (
          <span
            className={cn(
              "text-xs font-semibold font-mono px-1.5 py-0.5 rounded",
              isPositive
                ? "text-emerald-400 bg-emerald-500/10"
                : "text-rose-400 bg-rose-500/10"
            )}
          >
            {delta}
          </span>
        )}
      </div>

      {subtext && (
        <p className="text-[11px] text-slate-500 mt-1 font-mono">{subtext}</p>
      )}
    </div>
  );
}
