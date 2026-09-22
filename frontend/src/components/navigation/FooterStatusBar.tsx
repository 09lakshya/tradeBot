"use client";

import React from "react";
import { Database, Server, Cpu, Globe, Wifi, WifiOff } from "lucide-react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { API_BASE_URL } from "@/services/client";

export function FooterStatusBar() {
  const { status, quality, latency, isFallback, reconnect } = useWebSocket();

  const getQualityBadge = () => {
    switch (quality) {
      case "EXCELLENT":
        return <span className="inline-flex items-center gap-1 text-emerald-400 font-semibold"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>WS ACTIVE ({latency > 0 ? `${latency}ms` : "<1ms"})</span>;
      case "GOOD":
        return <span className="inline-flex items-center gap-1 text-cyan-400 font-semibold"><span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>WS GOOD ({latency}ms)</span>;
      case "POOR":
        return <span className="inline-flex items-center gap-1 text-amber-400 font-semibold"><span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>WS SLOW ({latency}ms)</span>;
      case "OFFLINE":
      default:
        return (
          <button onClick={reconnect} className="inline-flex items-center gap-1 text-rose-400 hover:underline font-semibold cursor-pointer" title="Click to reconnect">
            <span className="w-1.5 h-1.5 rounded-full bg-rose-400"></span>HTTP FALLBACK (WS DISCONNECTED)
          </button>
        );
    }
  };

  return (
    <footer className="h-7 border-t border-slate-800 bg-slate-950 text-slate-400 text-[11px] font-mono px-3 flex items-center justify-between select-none z-30 fixed bottom-0 left-0 right-0">
      {/* Left items */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <Server className="w-3 h-3 text-emerald-400" />
          <span>API: <strong className="text-slate-200">{API_BASE_URL}</strong></span>
        </div>

        <div className="flex items-center gap-1.5">
          {status === "OPEN" ? <Wifi className="w-3 h-3 text-emerald-400" /> : <WifiOff className="w-3 h-3 text-rose-400" />}
          {getQualityBadge()}
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

