"use client";

import React from "react";
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import { RiskAnalytics } from "@/lib/types";
import { PieChart as PieIcon, BarChart2 } from "lucide-react";

interface AllocationChartsProps {
  riskData: RiskAnalytics | null;
}

const COLOR_PALETTE = [
  "#10b981", // Emerald
  "#06b6d4", // Cyan
  "#3b82f6", // Blue
  "#8b5cf6", // Purple
  "#f59e0b", // Amber
  "#f43f5e", // Rose
  "#ec4899", // Pink
  "#64748b", // Slate
];

export function AllocationCharts({ riskData }: AllocationChartsProps) {
  const sectorData = riskData
    ? Object.entries(riskData.sector_exposure).map(([name, value]) => ({
        name,
        value: Number(value.toFixed(1)),
      }))
    : [];

  const strategyData = riskData
    ? Object.entries(riskData.strategy_exposure).map(([name, value]) => ({
        name,
        value: Number(value.toFixed(1)),
      }))
    : [];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
      {/* Portfolio Strategy Allocation (Donut Chart) */}
      <div className="rounded-xl border border-[#1e293b] bg-[#111827]/80 backdrop-blur-md p-5 shadow-xl">
        <div className="flex items-center gap-2 mb-4 pb-3 border-b border-[#1e293b]">
          <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
            <PieIcon className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-slate-100">Portfolio Strategy Allocation</h4>
            <p className="text-xs text-slate-400 font-mono">Weight distribution across quant strategies</p>
          </div>
        </div>

        <div className="h-[250px] w-full flex items-center justify-center">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={strategyData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={85}
                paddingAngle={4}
                dataKey="value"
              >
                {strategyData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLOR_PALETTE[index % COLOR_PALETTE.length]} stroke="#0a0e17" strokeWidth={2} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  backgroundColor: "#0f172a",
                  borderColor: "#334155",
                  borderRadius: "10px",
                }}
                labelStyle={{ color: "#94a3b8", fontSize: "12px" }}
                formatter={(val: number) => [`${val}%`, "Allocation Weight"]}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Strategy Legend list */}
        <div className="mt-2 space-y-1.5">
          {strategyData.map((item, idx) => (
            <div key={item.name} className="flex items-center justify-between text-xs font-mono">
              <div className="flex items-center gap-2">
                <span
                  className="w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: COLOR_PALETTE[idx % COLOR_PALETTE.length] }}
                ></span>
                <span className="text-slate-300 truncate max-w-[200px]">{item.name}</span>
              </div>
              <span className="font-semibold text-slate-200">{item.value}%</span>
            </div>
          ))}
        </div>
      </div>

      {/* Sector Allocation (Horizontal Bar Chart) */}
      <div className="rounded-xl border border-[#1e293b] bg-[#111827]/80 backdrop-blur-md p-5 shadow-xl">
        <div className="flex items-center gap-2 mb-4 pb-3 border-b border-[#1e293b]">
          <div className="p-2 rounded-lg bg-purple-500/10 text-purple-400 border border-purple-500/20">
            <BarChart2 className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-slate-100">Sector Exposure Breakdown</h4>
            <p className="text-xs text-slate-400 font-mono">Concentration breakdown across industrial sectors</p>
          </div>
        </div>

        <div className="h-[250px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              layout="vertical"
              data={sectorData}
              margin={{ top: 5, right: 30, left: 40, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
              <XAxis type="number" stroke="#64748b" fontSize={11} tickFormatter={(val) => `${val}%`} />
              <YAxis
                type="category"
                dataKey="name"
                stroke="#64748b"
                fontSize={11}
                tickLine={false}
                width={120}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#0f172a",
                  borderColor: "#334155",
                  borderRadius: "10px",
                }}
                formatter={(val: number) => [`${val}%`, "Sector Exposure"]}
              />
              <Bar dataKey="value" fill="#8b5cf6" radius={[0, 4, 4, 0]}>
                {sectorData.map((_, index) => (
                  <Cell key={`sector-cell-${index}`} fill={COLOR_PALETTE[index % COLOR_PALETTE.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Cash Utilization Gauge sub-text */}
        {riskData && (
          <div className="mt-2 pt-3 border-t border-[#1e293b] flex items-center justify-between text-xs font-mono">
            <span className="text-slate-400">Capital Utilization:</span>
            <span className="font-semibold text-emerald-400">{riskData.cash_utilization_pct}%</span>
          </div>
        )}
      </div>
    </div>
  );
}
