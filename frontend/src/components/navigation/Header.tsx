"use client";

import React, { useState, useEffect } from "react";
import { Activity, Command, ShieldAlert, ShieldCheck, Zap, RefreshCw, Bell } from "lucide-react";
import { useUIStore } from "@/stores/useUIStore";
import { useCommandStore } from "@/stores/useCommandStore";
import { useNotificationStore } from "@/stores/useNotificationStore";
import { ThemeSelector } from "@/components/common/ThemeSelector";
import { operationsService } from "@/services/operations.service";
import type { ReadinessAssessment, SchedulerStatusResponse } from "@/types";

export function Header() {
  const { toggleCommandPalette } = useCommandStore();
  const { notifications, toggleNotificationCenter } = useNotificationStore();
  const [schedulerStatus, setSchedulerStatus] = useState<SchedulerStatusResponse | null>(null);
  const [readiness, setReadiness] = useState<ReadinessAssessment | null>(null);
  const [currentTime, setCurrentTime] = useState<string>("");

  const unreadCount = notifications.filter((n) => !n.read && !n.archived).length;

  const fetchHeaderTelemetry = async () => {
    try {
      const [sch, read] = await Promise.allSettled([
        operationsService.getSchedulerStatus(),
        operationsService.assessReadiness(),
      ]);
      if (sch.status === "fulfilled") setSchedulerStatus(sch.value);
      if (read.status === "fulfilled") setReadiness(read.value);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchHeaderTelemetry();
    const interval = setInterval(() => {
      const now = new Date();
      setCurrentTime(
        now.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false }) + " IST"
      );
    }, 1000);
  return () => clearInterval(interval);
  }, []);

  const isReady = readiness?.status === "READY FOR LIVE PILOT";

  return (
    <header className="h-14 border-b border-slate-800 bg-slate-950 px-4 flex items-center justify-between sticky top-0 z-40 select-none">
      {/* Left Title & Status */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
          <span className="font-bold text-sm bg-gradient-to-r from-emerald-400 to-cyan-400 bg-clip-text text-transparent">
            TRADE BOT
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 font-mono">
            v1.0-PROD
          </span>
        </div>

        <div className="h-4 w-px bg-slate-800 mx-1 hidden sm:block" />

        {/* Telemetry Pills */}
        <div className="hidden md:flex items-center gap-2 text-xs">
          <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-slate-900 border border-slate-800">
            <span className="text-slate-400">NSE/BSE:</span>
            <span className={schedulerStatus?.is_market_open ? "text-emerald-400 font-semibold" : "text-amber-400 font-semibold"}>
              {schedulerStatus?.is_market_open ? "OPEN (09:15-15:30)" : "CLOSED (PAPER MODE)"}
            </span>
          </div>

          <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-slate-900 border border-slate-800">
            <Zap className="w-3.5 h-3.5 text-cyan-400" />
            <span className="text-slate-400">Mode:</span>
            <span className="text-cyan-400 font-mono uppercase font-semibold">
              {schedulerStatus?.mode || "AUTONOMOUS"}
            </span>
          </div>

          <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-slate-900 border border-slate-800">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-slate-400">Readiness:</span>
            <span className={`font-mono font-bold ${isReady ? "text-emerald-400" : "text-slate-300"}`}>
              {readiness?.overall_score ?? 0}/100
            </span>
            {/* The label follows the assessed status; it used to always read
                "READY FOR LIVE PILOT", even at a score of 0. */}
            <span
              className={`text-[10px] px-1 rounded ${
 isReady ? "bg-emerald-500/20 text-emerald-300" : "bg-slate-700/40 text-slate-400"
              }`}
            >
              {readiness?.status ?? "NOT ASSESSED"}
            </span>
          </div>
        </div>
      </div>

      {/* Right Actions & Clock */}
      <div className="flex items-center gap-3">
        <ThemeSelector />

        <span className="font-mono text-xs text-slate-400 hidden lg:inline-block">
          {currentTime || "09:15:00 IST"}
        </span>

        {/* Command Palette Button */}
        <button
          onClick={toggleCommandPalette}
          className="flex items-center gap-2 px-2.5 py-1 rounded bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-slate-200 text-xs transition-colors"
        >
          <Command className="w-3.5 h-3.5 text-slate-400" />
          <span className="hidden sm:inline">Search / Cmd</span>
          <kbd className="px-1 py-0.5 text-[10px] bg-slate-800 text-slate-400 rounded font-mono">
            ⌘K
          </kbd>
        </button>

        {/* Refresh button */}
        <button
          onClick={fetchHeaderTelemetry}
          className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
          title="Refresh Telemetry"
        >
          <RefreshCw className="w-4 h-4" />
        </button>

        {/* Notification Bell Button */}
        <div className="relative">
          <button
            onClick={toggleNotificationCenter}
            className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors relative"
            title="Open Notification Center"
          >
            <Bell className="w-4 h-4" />
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 px-1 py-0.2 text-[9px] font-bold font-mono rounded-full bg-emerald-500 text-slate-950 animate-pulse">
                {unreadCount}
              </span>
            )}
          </button>
        </div>
      </div>
    </header>
  );
}

