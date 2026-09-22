"use client";

import React, { useEffect } from "react";
import { useUIStore, ThemeMode, AccentColor } from "@/stores/useUIStore";
import { Sun, Moon, Contrast, Palette } from "lucide-react";

export function ThemeSelector() {
  const { theme, setTheme, accentColor, setAccentColor } = useUIStore();

  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove("dark", "light", "theme-high-contrast");

    if (theme === "dark") {
      root.classList.add("dark");
    } else if (theme === "light") {
      root.classList.add("light");
    } else if (theme === "high-contrast") {
      root.classList.add("dark", "theme-high-contrast");
    }
  }, [theme]);

  return (
    <div className="flex items-center gap-2 font-mono text-xs">
      {/* Theme Switcher */}
      <div className="flex items-center bg-slate-900 border border-slate-800 p-0.5 rounded-lg">
        <button
          onClick={() => setTheme("dark")}
          className={`p-1.5 rounded transition ${
            theme === "dark" ? "bg-slate-800 text-emerald-400 font-bold" : "text-slate-400 hover:text-slate-200"
          }`}
          title="Dark Mode"
        >
          <Moon className="w-3.5 h-3.5" />
        </button>

        <button
          onClick={() => setTheme("light")}
          className={`p-1.5 rounded transition ${
            theme === "light" ? "bg-slate-200 text-slate-900 font-bold" : "text-slate-400 hover:text-slate-200"
          }`}
          title="Light Mode"
        >
          <Sun className="w-3.5 h-3.5" />
        </button>

        <button
          onClick={() => setTheme("high-contrast")}
          className={`p-1.5 rounded transition ${
            theme === "high-contrast"
              ? "bg-amber-400 text-slate-950 font-bold"
              : "text-slate-400 hover:text-slate-200"
          }`}
          title="High Contrast Mode"
        >
          <Contrast className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Accent Color Palette */}
      <div className="hidden sm:flex items-center gap-1 bg-slate-900 border border-slate-800 px-2 py-1 rounded-lg">
        <Palette className="w-3 h-3 text-slate-400" />
        {(["emerald", "blue", "violet", "amber", "crimson"] as AccentColor[]).map((c) => (
          <button
            key={c}
            onClick={() => setAccentColor(c)}
            className={`w-3 h-3 rounded-full border transition ${
              accentColor === c ? "scale-125 ring-2 ring-white" : "opacity-70 hover:opacity-100"
            } ${
              c === "emerald"
                ? "bg-emerald-500 border-emerald-400"
                : c === "blue"
                ? "bg-blue-500 border-blue-400"
                : c === "violet"
                ? "bg-purple-500 border-purple-400"
                : c === "amber"
                ? "bg-amber-500 border-amber-400"
                : "bg-rose-500 border-rose-400"
            }`}
            title={`Accent: ${c}`}
          />
        ))}
      </div>
    </div>
  );
}
