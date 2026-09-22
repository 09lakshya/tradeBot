"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Radio,
  Briefcase,
  ShoppingBag,
  Layers,
  Cpu,
  Wrench,
  PieChart,
  ShieldAlert,
  History,
  Scan,
  HelpCircle,
  LineChart,
  Server,
  ShieldCheck,
  Settings,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { useUIStore } from "@/stores/useUIStore";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/live", label: "Live Trading", icon: Radio },
  { href: "/portfolio", label: "Portfolio", icon: Briefcase },
  { href: "/orders", label: "Orders", icon: ShoppingBag },
  { href: "/positions", label: "Positions", icon: Layers },
  { href: "/strategies", label: "Strategies", icon: Cpu },
  { href: "/strategy-builder", label: "Strategy Builder", icon: Wrench },
  { href: "/portfolio-construction", label: "Portfolio Construction", icon: PieChart },
  { href: "/risk", label: "Risk Dashboard", icon: ShieldAlert },
  { href: "/backtest", label: "Backtesting", icon: History },
  { href: "/market-scanner", label: "Market Scanner", icon: Scan },
  { href: "/explainability", label: "Explainability", icon: HelpCircle },
  { href: "/analytics", label: "Analytics", icon: LineChart },
  { href: "/operations", label: "Operations", icon: Server },
  { href: "/validation", label: "Validation Dashboard", icon: ShieldCheck },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { sidebarCollapsed, toggleSidebar } = useUIStore();

  return (
    <aside
      className={cn(
        "h-[calc(100vh-3.5rem)] border-r border-slate-800 bg-slate-950 flex flex-col justify-between transition-all duration-200 select-none z-30 sticky top-14",
        sidebarCollapsed ? "w-14" : "w-60"
      )}
    >
      {/* Nav List */}
      <div className="py-2 px-1.5 space-y-1 overflow-y-auto custom-scrollbar">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-2.5 py-2 rounded-md text-xs font-medium transition-colors group relative",
                isActive
                  ? "bg-slate-800/80 text-emerald-400 border border-slate-700/50 shadow-sm"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-900/60"
              )}
              title={sidebarCollapsed ? item.label : undefined}
            >
              <Icon className={cn("w-4 h-4 shrink-0", isActive ? "text-emerald-400" : "text-slate-400 group-hover:text-slate-200")} />
              {!sidebarCollapsed && <span className="truncate">{item.label}</span>}
              {isActive && (
                <div className="absolute right-0 top-1/2 -translate-y-1/2 w-1 h-5 bg-emerald-500 rounded-l" />
              )}
            </Link>
          );
        })}
      </div>

      {/* Collapse Toggle */}
      <div className="p-2 border-t border-slate-800 flex justify-end">
        <button
          onClick={toggleSidebar}
          className="p-1.5 rounded hover:bg-slate-900 text-slate-400 hover:text-slate-200 w-full flex items-center justify-center transition-colors"
          title={sidebarCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
        >
          {sidebarCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
      </div>
    </aside>
  );
}
