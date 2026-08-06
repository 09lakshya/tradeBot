import { create } from "zustand";

interface WorkspaceState {
  activeSymbol: string;
  activeTimeframe: string;
  activeStrategyId: string | null;
  dateRange: { start: string; end: string };
  setActiveSymbol: (symbol: string) => void;
  setActiveTimeframe: (tf: string) => void;
  setActiveStrategyId: (id: string | null) => void;
  setDateRange: (range: { start: string; end: string }) => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  activeSymbol: "RELIANCE.NS",
  activeTimeframe: "1d",
  activeStrategyId: null,
  dateRange: { start: "2026-08-01", end: "2026-08-06" },
  setActiveSymbol: (symbol) => set({ activeSymbol: symbol }),
  setActiveTimeframe: (tf) => set({ activeTimeframe: tf }),
  setActiveStrategyId: (id) => set({ activeStrategyId: id }),
  setDateRange: (range) => set({ dateRange: range }),
}));
