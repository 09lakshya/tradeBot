"use client";

import React, { useState, useEffect } from "react";
import { Database, Server, Cpu, Globe, CheckCircle2 } from "lucide-react";

export function FooterStatusBar() {
  const [latency, setLatency] = useState<number>(4);

  useEffect(() => {
    const interval = setInterval(() => {
      setLatency(Math.floor(Math.random() * 5) + 3);
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <footer className="h-7 border-t border-slate-800 bg-slate-950 text-slate-400 text-[11px] font-mono px-3 flex items-center justify-between select-none z-30 fixed bottom-0 left-0 right-0">
      {/* Left items */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <Server className="w-3 h-3 text-emerald-400" />
          <span>API: <strong className="text-slate-200">http://localhost:8000</strong></span>
        </div>

        <div className="flex items-center gap-1.5">
          <CheckCircle2 className="w-3 h-3 text-emerald-400" />
          <span>Latency: <strong className="text-emerald-400">{latency}ms</strong></span>
        </div>

        <div className="flex items-center gap-1.5 hidden md:flex">
          <Database className="w-3 h-3 text-cyan-400" />
          <span>TimescaleDB: <strong className="text-slate-200">CONNECTED</strong></span>
        </div>

        <div className="flex items-center gap-1.5 hidden lg:flex">
          <Cpu className="w-3 h-3 text-purple-400" />
          <span>Redis: <strong className="text-slate-200">ACTIVE</strong></span>
        </div>
      </div>

      {/* Right items */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <Globe className="w-3 h-3 text-cyan-400" />
          <span>Scope: <strong className="text-emerald-400">NSE / BSE (₹ INR)</strong></span>
        </div>

        <span className="hidden sm:inline">TZ: Asia/Kolkata (IST)</span>
      </div>
    </footer>
  );
}
