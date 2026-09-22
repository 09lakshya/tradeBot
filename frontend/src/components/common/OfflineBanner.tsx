"use client";

import React from "react";
import { useOnlineStatus } from "@/hooks/useOnlineStatus";
import { WifiOff, RefreshCw } from "lucide-react";

export function OfflineBanner() {
  const isOnline = useOnlineStatus();

  if (isOnline) return null;

  return (
    <div className="bg-rose-600 text-white font-mono text-xs px-4 py-2 flex items-center justify-between shadow-lg border-b border-rose-700 z-40 sticky top-0">
      <div className="flex items-center gap-2 font-semibold">
        <WifiOff className="w-4 h-4 animate-bounce" />
        <span>OFFLINE MODE: Network connection severed. Displaying cached operational state.</span>
      </div>
      <button
        onClick={() => window.location.reload()}
        className="px-2.5 py-1 bg-rose-800 hover:bg-rose-900 text-white text-[11px] rounded font-bold flex items-center gap-1 border border-rose-700"
      >
        <RefreshCw className="w-3 h-3" />
        Reconnect
      </button>
    </div>
  );
}
