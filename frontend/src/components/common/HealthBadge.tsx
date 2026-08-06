import React from "react";
import { cn } from "@/lib/utils";

interface HealthBadgeProps {
  status: "healthy" | "degraded" | "critical" | "nominal" | string;
  label?: string;
  className?: string;
}

export function HealthBadge({ status, label, className }: HealthBadgeProps) {
  const s = status.toLowerCase();
  const isHealthy = s === "healthy" || s === "nominal" || s === "passed";
  const isDegraded = s === "degraded" || s === "warning";
  const isCritical = s === "critical" || s === "error" || s === "failed";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-mono font-semibold uppercase tracking-wider",
        isHealthy && "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
        isDegraded && "bg-amber-500/10 text-amber-400 border border-amber-500/20",
        isCritical && "bg-rose-500/10 text-rose-400 border border-rose-500/20",
        !isHealthy && !isDegraded && !isCritical && "bg-slate-800 text-slate-300 border border-slate-700",
        className
      )}
    >
      <span
        className={cn(
          "w-1.5 h-1.5 rounded-full",
          isHealthy && "bg-emerald-400 animate-pulse",
          isDegraded && "bg-amber-400 animate-ping",
          isCritical && "bg-rose-400 animate-pulse",
          !isHealthy && !isDegraded && !isCritical && "bg-slate-400"
        )}
      />
      {label || status}
    </span>
  );
}
