"use client";

import React from "react";
import { Sparkles } from "lucide-react";

interface EmptyStateProps {
  title?: string;
  description?: string;
  actionText?: string;
  onAction?: () => void;
  icon?: React.ReactNode;
}

export function EmptyState({
  title = "No Data Found",
  description = "No matching records or active telemetry items found in the current workspace view.",
  actionText,
  onAction,
  icon,
}: EmptyStateProps) {
  return (
    <div className="p-8 bg-slate-900/60 border border-slate-800 rounded-xl text-center font-mono space-y-3 my-4 ">
      <div className="w-12 h-12 rounded-full bg-slate-800 border border-slate-700 text-slate-400 flex items-center justify-center mx-auto">
        {icon || <Sparkles className="w-6 h-6 text-emerald-400" />}
      </div>
      <h4 className="text-sm font-bold text-slate-200">{title}</h4>
      <p className="text-xs text-slate-400 max-w-sm mx-auto leading-relaxed">{description}</p>
      {actionText && onAction && (
        <button
          onClick={onAction}
          className="mt-2 px-3.5 py-1.5 text-xs bg-emerald-600 hover:bg-emerald-500 text-white font-medium rounded-lg inline-flex items-center gap-1.5 shadow"
        >
          {actionText}
        </button>
      )}
    </div>
  );
}
