"use client";

import React from "react";
import { Keyboard, X } from "lucide-react";

interface ShortcutHelpModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ShortcutHelpModal({ isOpen, onClose }: ShortcutHelpModalProps) {
  if (!isOpen) return null;

  const shortcuts = [
    { key: "Ctrl + K / Cmd + K", desc: "Open Command Palette" },
    { key: "Ctrl + B / Cmd + B", desc: "Toggle Navigation Sidebar" },
    { key: "Ctrl + Shift + R", desc: "Hard Refresh Dashboard" },
    { key: "Esc", desc: "Dismiss Active Modal / Drawer" },
    { key: "? or Ctrl + /", desc: "Toggle Keyboard Shortcut Legend" },
    { key: "F1", desc: "Go to Main Dashboard" },
    { key: "F2", desc: "Go to Orders & Fills" },
    { key: "F3", desc: "Go to Positions & Holdings" },
    { key: "F4", desc: "Go to Risk Controls" },
    { key: "F5", desc: "Go to Strategy Registry" },
    { key: "F6", desc: "Go to Portfolio Construction" },
    { key: "F7", desc: "Go to Performance Analytics" },
    { key: "F8", desc: "Go to Market Scanner" },
    { key: "F9", desc: "Go to Backtest Execution" },
    { key: "F10", desc: "Go to Operations Command Center" },
    { key: "F11", desc: "Go to Trade Explainability" },
    { key: "F12", desc: "Go to System Settings" },
  ];

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 max-w-lg w-full shadow-2xl space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <Keyboard className="w-5 h-5 text-emerald-400" />
            <h3 className="text-sm font-bold text-slate-100 uppercase tracking-wider">
              Keyboard Shortcuts Legend
            </h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-100">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs font-mono max-h-[400px] overflow-y-auto pr-1">
          {shortcuts.map((s, idx) => (
            <div
              key={idx}
              className="flex items-center justify-between p-2 rounded bg-slate-950 border border-slate-800/80"
            >
              <span className="text-slate-400">{s.desc}</span>
              <kbd className="px-2 py-0.5 rounded bg-slate-800 text-emerald-300 font-semibold border border-slate-700 text-[11px]">
                {s.key}
              </kbd>
            </div>
          ))}
        </div>

        <div className="pt-2 text-center text-[11px] text-slate-500 font-mono">
          Press <kbd className="text-slate-400 bg-slate-800 px-1 py-0.5 rounded">Esc</kbd> anytime to exit.
        </div>
      </div>
    </div>
  );
}
