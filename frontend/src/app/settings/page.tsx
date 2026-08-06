"use client";

import React, { useState } from "react";
import { Settings as SettingsIcon, Save, Key, Shield, Bell, Database } from "lucide-react";

export default function SettingsPage() {
  const [maxDrawdown, setMaxDrawdown] = useState<number>(10.0);
  const [maxLeverage, setMaxLeverage] = useState<number>(1.5);
  const [varLimit, setVarLimit] = useState<number>(2.5);
  const [isSaved, setIsSaved] = useState<boolean>(false);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 2000);
  };

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="pb-2 border-b border-slate-800">
        <h1 className="text-xl font-bold text-slate-100 font-mono tracking-tight flex items-center gap-2">
          <SettingsIcon className="w-5 h-5 text-emerald-400" /> Platform & Risk Engine Settings
        </h1>
        <p className="text-xs text-slate-400 font-mono">
          Global risk thresholds, paper broker parameters, API keys, and notification triggers
        </p>
      </div>

      <form onSubmit={handleSave} className="space-y-6 font-mono text-xs">
        {/* Risk Thresholds */}
        <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4">
          <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
            <Shield className="w-4 h-4 text-rose-400" /> Pre-Trade Risk Engine Limits
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-slate-400 mb-1">Max Drawdown Limit (%)</label>
              <input
                type="number"
                step="0.5"
                value={maxDrawdown}
                onChange={(e) => setMaxDrawdown(Number(e.target.value))}
                className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-slate-100 outline-none focus:border-emerald-500"
              />
            </div>

            <div>
              <label className="block text-slate-400 mb-1">Max Gross Leverage (x)</label>
              <input
                type="number"
                step="0.1"
                value={maxLeverage}
                onChange={(e) => setMaxLeverage(Number(e.target.value))}
                className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-slate-100 outline-none focus:border-emerald-500"
              />
            </div>

            <div>
              <label className="block text-slate-400 mb-1">VaR 95% Limit (%)</label>
              <input
                type="number"
                step="0.1"
                value={varLimit}
                onChange={(e) => setVarLimit(Number(e.target.value))}
                className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-slate-100 outline-none focus:border-emerald-500"
              />
            </div>
          </div>
        </div>

        {/* API Credentials */}
        <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4">
          <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
            <Key className="w-4 h-4 text-cyan-400" /> Market Data & Broker API Endpoints
          </h3>

          <div className="space-y-3">
            <div>
              <label className="block text-slate-400 mb-1">FastAPI Backend URL</label>
              <input
                type="text"
                defaultValue="http://localhost:8000"
                className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-slate-100 outline-none focus:border-emerald-500"
              />
            </div>

            <div>
              <label className="block text-slate-400 mb-1">Indian Market Data Feed Source</label>
              <select className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-slate-100 outline-none">
                <option value="nse_yahoo">NSE / BSE Yahoo Finance Realtime Provider</option>
                <option value="zerodha_kite_sim">Zerodha Kite Simulator (Paper)</option>
              </select>
            </div>
          </div>
        </div>

        <button
          type="submit"
          className="px-5 py-2.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold font-mono text-xs flex items-center gap-2 transition-colors shadow-lg"
        >
          <Save className="w-4 h-4" />
          {isSaved ? "Settings Saved Successfully!" : "Save Platform Configuration"}
        </button>
      </form>
    </div>
  );
}
