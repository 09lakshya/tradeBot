"use client";

import React, { useState } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
  ReferenceLine,
} from "recharts";
import { EquityCurvePoint, DrawdownPoint, DailyReturnPoint, MonthlyReturnPoint } from "@/lib/types";
import { formatCurrency, formatPercent } from "@/lib/utils";
import { TrendingUp, Layers, Activity, Calendar } from "lucide-react";

interface EquityDrawdownChartsProps {
  equityPoints: EquityCurvePoint[];
  drawdownPoints: DrawdownPoint[];
  dailyReturns: DailyReturnPoint[];
  monthlyReturns: MonthlyReturnPoint[];
}

export function EquityDrawdownCharts({
  equityPoints,
  drawdownPoints,
  dailyReturns,
  monthlyReturns,
}: EquityDrawdownChartsProps) {
  const [activeTab, setActiveTab] = useState<"equity" | "drawdown" | "daily" | "monthly">("equity");

  // Format tick values for Y axis
  const formatYAxisCurrency = (value: number) => {
    if (value >= 10000000) return `₹${(value / 10000000).toFixed(2)}Cr`;
    if (value >= 100000) return `₹${(value / 100000).toFixed(1)}L`;
    if (value >= 1000) return `₹${(value / 1000).toFixed(0)}k`;
    return `₹${value}`;
  };

  return (
    <div className="rounded-xl border border-[#1e293b] bg-[#111827]/80 backdrop-blur-md p-5 shadow-xl">
      {/* Header controls & tabs */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 pb-4 border-b border-[#1e293b]">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <TrendingUp className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
              Performance & Portfolio Analytics
            </h3>
            <p className="text-xs text-slate-400 font-mono">
              Real-time mark-to-market performance, equity curves, drawdown & returns
            </p>
          </div>
        </div>

        {/* Tab switcher buttons */}
        <div className="flex items-center p-1 bg-[#0a0e17] rounded-xl border border-[#1e293b] text-xs font-mono">
          <button
            onClick={() => setActiveTab("equity")}
            className={`px-3 py-1.5 rounded-lg transition-all flex items-center gap-1.5 ${
              activeTab === "equity"
                ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-semibold shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            Gross vs Net Equity
          </button>
          <button
            onClick={() => setActiveTab("drawdown")}
            className={`px-3 py-1.5 rounded-lg transition-all flex items-center gap-1.5 ${
              activeTab === "drawdown"
                ? "bg-rose-500/20 text-rose-400 border border-rose-500/30 font-semibold shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Activity className="w-3.5 h-3.5" />
            Drawdown %
          </button>
          <button
            onClick={() => setActiveTab("daily")}
            className={`px-3 py-1.5 rounded-lg transition-all flex items-center gap-1.5 ${
              activeTab === "daily"
                ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 font-semibold shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Activity className="w-3.5 h-3.5" />
            Daily Returns
          </button>
          <button
            onClick={() => setActiveTab("monthly")}
            className={`px-3 py-1.5 rounded-lg transition-all flex items-center gap-1.5 ${
              activeTab === "monthly"
                ? "bg-purple-500/20 text-purple-400 border border-purple-500/30 font-semibold shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Calendar className="w-3.5 h-3.5" />
            Monthly Returns
          </button>
        </div>
      </div>

      {/* Chart Canvas Container */}
      <div className="h-[380px] w-full">
        {/* Tab 1: Gross vs Net Equity Curve */}
        {activeTab === "equity" && (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={equityPoints} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
              <defs>
                <linearGradient id="grossGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                </linearGradient>
                <linearGradient id="netGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#06b6d4" stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis
                dataKey="timestamp"
                stroke="#64748b"
                fontSize={11}
                tickLine={false}
                tickFormatter={(val) => val.split("-").slice(1).join("/")}
              />
              <YAxis
                stroke="#64748b"
                fontSize={11}
                tickLine={false}
                domain={["auto", "auto"]}
                tickFormatter={formatYAxisCurrency}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#0f172a",
                  borderColor: "#334155",
                  borderRadius: "10px",
                  boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.5)",
                }}
                labelStyle={{ color: "#94a3b8", fontSize: "12px", fontFamily: "monospace" }}
                formatter={(val: number, name: string) => [
                  formatCurrency(val),
                  name === "gross_equity" ? "Gross Equity" : "Net Equity",
                ]}
              />
              <Legend
                wrapperStyle={{ paddingTop: "10px", fontSize: "12px" }}
                formatter={(val) => (val === "gross_equity" ? "Gross Equity Value" : "Net Portfolio Value")}
              />
              <Area
                type="monotone"
                dataKey="gross_equity"
                stroke="#10b981"
                strokeWidth={2.5}
                fillOpacity={1}
                fill="url(#grossGradient)"
              />
              <Area
                type="monotone"
                dataKey="net_equity"
                stroke="#06b6d4"
                strokeWidth={2}
                strokeDasharray="4 2"
                fillOpacity={1}
                fill="url(#netGradient)"
              />
            </AreaChart>
          </ResponsiveContainer>
        )}

        {/* Tab 2: Drawdown Curve */}
        {activeTab === "drawdown" && (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={drawdownPoints} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
              <defs>
                <linearGradient id="drawdownGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#f43f5e" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis
                dataKey="timestamp"
                stroke="#64748b"
                fontSize={11}
                tickLine={false}
                tickFormatter={(val) => val.split("-").slice(1).join("/")}
              />
              <YAxis
                stroke="#64748b"
                fontSize={11}
                tickLine={false}
                domain={["auto", 0]}
                tickFormatter={(val) => `${val}%`}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#0f172a",
                  borderColor: "#334155",
                  borderRadius: "10px",
                  boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.5)",
                }}
                labelStyle={{ color: "#94a3b8", fontSize: "12px", fontFamily: "monospace" }}
                formatter={(val: number) => [`${val}%`, "Peak Drawdown"]}
              />
              <ReferenceLine y={0} stroke="#475569" strokeDasharray="2 2" />
              <Area
                type="monotone"
                dataKey="drawdown_pct"
                stroke="#f43f5e"
                strokeWidth={2}
                fillOpacity={1}
                fill="url(#drawdownGradient)"
              />
            </AreaChart>
          </ResponsiveContainer>
        )}

        {/* Tab 3: Daily Returns */}
        {activeTab === "daily" && (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={dailyReturns} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis
                dataKey="date"
                stroke="#64748b"
                fontSize={11}
                tickLine={false}
                tickFormatter={(val) => val.split("-").slice(1).join("/")}
              />
              <YAxis
                stroke="#64748b"
                fontSize={11}
                tickLine={false}
                tickFormatter={(val) => `${val}%`}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#0f172a",
                  borderColor: "#334155",
                  borderRadius: "10px",
                }}
                labelStyle={{ color: "#94a3b8", fontSize: "12px" }}
                formatter={(val: number, name: string) => [
                  `${val > 0 ? "+" : ""}${val}%`,
                  name === "gross_return_pct" ? "Gross Daily Return" : "Net Daily Return",
                ]}
              />
              <ReferenceLine y={0} stroke="#475569" />
              <Bar dataKey="gross_return_pct" name="Gross Return %" fill="#10b981" radius={[4, 4, 0, 0]} />
              <Bar dataKey="net_return_pct" name="Net Return %" fill="#06b6d4" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}

        {/* Tab 4: Monthly Returns */}
        {activeTab === "monthly" && (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={monthlyReturns} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis dataKey="month" stroke="#64748b" fontSize={11} tickLine={false} />
              <YAxis
                stroke="#64748b"
                fontSize={11}
                tickLine={false}
                tickFormatter={(val) => `${val}%`}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#0f172a",
                  borderColor: "#334155",
                  borderRadius: "10px",
                }}
                labelStyle={{ color: "#94a3b8", fontSize: "12px" }}
                formatter={(val: number, name: string) => [
                  `${val > 0 ? "+" : ""}${val}%`,
                  name === "gross_return_pct" ? "Gross Return %" : "Net Return %",
                ]}
              />
              <ReferenceLine y={0} stroke="#475569" />
              <Bar dataKey="gross_return_pct" name="Gross Return %" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
              <Bar dataKey="net_return_pct" name="Net Return %" fill="#3b82f6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
