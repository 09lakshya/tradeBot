"use client";

import React from "react";

export function MetricSkeleton() {
  return (
    <div className="p-4 rounded-xl border border-[#1e293b] bg-[#111827]/70 animate-pulse">
      <div className="flex justify-between items-center mb-3">
        <div className="h-3 w-24 bg-slate-800 rounded"></div>
        <div className="h-4 w-4 bg-slate-800 rounded-full"></div>
      </div>
      <div className="h-7 w-32 bg-slate-800 rounded mb-2"></div>
      <div className="h-3 w-20 bg-slate-800/60 rounded"></div>
    </div>
  );
}

export function ChartSkeleton({ height = "h-72" }: { height?: string }) {
  return (
    <div className={`p-5 rounded-xl border border-[#1e293b] bg-[#111827]/70 animate-pulse ${height} flex flex-col justify-between`}>
      <div className="flex justify-between items-center">
        <div className="h-4 w-40 bg-slate-800 rounded"></div>
        <div className="h-6 w-24 bg-slate-800 rounded"></div>
      </div>
      <div className="flex-1 my-4 bg-slate-800/30 rounded flex items-end justify-between p-4 gap-2">
        <div className="w-full h-1/3 bg-slate-800/50 rounded"></div>
        <div className="w-full h-1/2 bg-slate-800/50 rounded"></div>
        <div className="w-full h-2/3 bg-slate-800/50 rounded"></div>
        <div className="w-full h-1/4 bg-slate-800/50 rounded"></div>
        <div className="w-full h-3/4 bg-slate-800/50 rounded"></div>
        <div className="w-full h-1/2 bg-slate-800/50 rounded"></div>
      </div>
      <div className="flex justify-between">
        <div className="h-3 w-16 bg-slate-800 rounded"></div>
        <div className="h-3 w-16 bg-slate-800 rounded"></div>
        <div className="h-3 w-16 bg-slate-800 rounded"></div>
      </div>
    </div>
  );
}

export function TableSkeleton() {
  return (
    <div className="p-5 rounded-xl border border-[#1e293b] bg-[#111827]/70 animate-pulse">
      <div className="h-5 w-48 bg-slate-800 rounded mb-4"></div>
      <div className="space-y-3">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-10 w-full bg-slate-800/40 rounded flex items-center justify-between px-4">
            <div className="h-3 w-20 bg-slate-800 rounded"></div>
            <div className="h-3 w-16 bg-slate-800 rounded"></div>
            <div className="h-3 w-24 bg-slate-800 rounded"></div>
            <div className="h-3 w-14 bg-slate-800 rounded"></div>
          </div>
        ))}
      </div>
    </div>
  );
}
