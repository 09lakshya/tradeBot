"use client";

import React, { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Search, Command, X, ArrowRight, Zap, Shield, FileText } from "lucide-react";
import { useCommandStore } from "@/stores/useCommandStore";
import { operationsService } from "@/services/operations.service";

const COMMAND_LINKS = [
  { label: "Go to Dashboard", href: "/", icon: "📈" },
  { label: "Go to Portfolio", href: "/portfolio", icon: "💼" },
  { label: "Go to Orders", href: "/orders", icon: "🛍️" },
  { label: "Go to Positions", href: "/positions", icon: "📚" },
  { label: "Go to Strategies", href: "/strategies", icon: "🤖" },
  { label: "Go to Strategy Builder", href: "/strategy-builder", icon: "🛠️" },
  { label: "Go to Portfolio Construction", href: "/portfolio-construction", icon: "🍰" },
  { label: "Go to Risk Dashboard", href: "/risk", icon: "🛡️" },
  { label: "Go to Backtesting", href: "/backtest", icon: "⌛" },
  { label: "Go to Market Scanner", href: "/market-scanner", icon: "🔍" },
  { label: "Go to Explainability", href: "/explainability", icon: "🧠" },
  { label: "Go to Analytics", href: "/analytics", icon: "📊" },
  { label: "Go to Operations", href: "/operations", icon: "🖥️" },
  { label: "Go to Settings", href: "/settings", icon: "⚙️" },
];

export function CommandPalette() {
  const router = useRouter();
  const { isOpen, query, closeCommandPalette, toggleCommandPalette, setQuery } = useCommandStore();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        toggleCommandPalette();
      }
      if (e.key === "Escape" && isOpen) {
        closeCommandPalette();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, toggleCommandPalette, closeCommandPalette]);

  if (!isOpen) return null;

  const filteredLinks = COMMAND_LINKS.filter((item) =>
    item.label.toLowerCase().includes(query.toLowerCase())
  );

  const handleSelectLink = (href: string) => {
    router.push(href);
    closeCommandPalette();
  };

  const handleQuickAction = async (actionType: string) => {
    try {
      if (actionType === "snapshot") {
        await operationsService.createSnapshot();
      } else if (actionType === "pause_scheduler") {
        await operationsService.controlScheduler("pause");
      }
    } catch (e) {
      console.error(e);
    } finally {
      closeCommandPalette();
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-start justify-center pt-20 px-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl w-full max-w-xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Search Input */}
        <div className="flex items-center px-4 py-3 border-b border-slate-800 gap-3">
          <Search className="w-4 h-4 text-slate-400" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type a command, page name, or ticker (e.g. RELIANCE.NS)..."
            className="bg-transparent text-sm text-slate-100 placeholder-slate-500 outline-none w-full font-mono"
            autoFocus
          />
          <button
            onClick={closeCommandPalette}
            className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Action Shortcuts */}
        <div className="p-2 border-b border-slate-800/80 bg-slate-950/50 flex gap-2 overflow-x-auto text-xs">
          <button
            onClick={() => handleQuickAction("snapshot")}
            className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-emerald-400 font-mono flex items-center gap-1.5 shrink-0"
          >
            <Zap className="w-3 h-3" /> Trigger EOD Snapshot
          </button>
          <button
            onClick={() => handleQuickAction("pause_scheduler")}
            className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-amber-400 font-mono flex items-center gap-1.5 shrink-0"
          >
            <Shield className="w-3 h-3" /> Pause Scheduler
          </button>
        </div>

        {/* Results List */}
        <div className="max-h-72 overflow-y-auto p-2 space-y-1 custom-scrollbar">
          {filteredLinks.length === 0 ? (
            <div className="p-4 text-center text-xs text-slate-500">
              No matching commands or pages found.
            </div>
          ) : (
            filteredLinks.map((item, idx) => (
              <button
                key={idx}
                onClick={() => handleSelectLink(item.href)}
                className="w-full text-left px-3 py-2 rounded.md hover:bg-slate-800 flex items-center justify-between text-xs text-slate-200 group transition-colors"
              >
                <div className="flex items-center gap-2.5">
                  <span className="text-base">{item.icon}</span>
                  <span className="font-medium">{item.label}</span>
                </div>
                <ArrowRight className="w-3.5 h-3.5 text-slate-500 group-hover:text-emerald-400 group-hover:translate-x-0.5 transition-all" />
              </button>
            ))
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-4 py-2 bg-slate-950 border-t border-slate-800/80 text-[11px] text-slate-500 flex justify-between font-mono">
          <span>Use ↑ ↓ to navigate</span>
          <span>ESC to exit</span>
        </div>
      </div>
    </div>
  );
}
