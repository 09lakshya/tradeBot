import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface WidgetConfig {
  id: string;
  title: string;
  type: string;
  colSpan?: number;
  rowSpan?: number;
  visible: boolean;
}

export interface WorkspaceLayout {
  id: string;
  name: string;
  description: string;
  isPreset?: boolean;
  activeSymbol: string;
  activeTimeframe: string;
  widgets: WidgetConfig[];
  updatedAt: string;
}

const DEFAULT_PRESETS: WorkspaceLayout[] = [
  {
    id: "trading-default",
    name: "Trading Operations",
    description: "Real-time charts, order entry, positions, and live quotes.",
    isPreset: true,
    activeSymbol: "RELIANCE.NS",
    activeTimeframe: "1d",
    updatedAt: new Date().toISOString(),
    widgets: [
      { id: "chart", title: "Price Action Chart", type: "CHART", colSpan: 2, rowSpan: 2, visible: true },
      { id: "positions", title: "Active Positions", type: "POSITIONS", colSpan: 1, rowSpan: 1, visible: true },
      { id: "trades", title: "Order Book & Trades", type: "TRADES", colSpan: 1, rowSpan: 1, visible: true },
      { id: "metrics", title: "Portfolio Performance Metrics", type: "METRICS", colSpan: 2, rowSpan: 1, visible: true },
    ],
  },
  {
    id: "risk-ops",
    name: "Risk & Compliance",
    description: "VaR limits, drawdown monitoring, and risk rule triggers.",
    isPreset: true,
    activeSymbol: "NIFTY50",
    activeTimeframe: "1d",
    updatedAt: new Date().toISOString(),
    widgets: [
      { id: "metrics", title: "Risk Metrics", type: "METRICS", colSpan: 2, rowSpan: 1, visible: true },
      { id: "positions", title: "Exposures & Concentration", type: "POSITIONS", colSpan: 2, rowSpan: 1, visible: true },
      { id: "chart", title: "Drawdown Curve", type: "CHART", colSpan: 2, rowSpan: 2, visible: true },
    ],
  },
  {
    id: "analytics-builder",
    name: "Strategy & Analytics",
    description: "Alpha signals, backtest execution, and explainability.",
    isPreset: true,
    activeSymbol: "TCS.NS",
    activeTimeframe: "1h",
    updatedAt: new Date().toISOString(),
    widgets: [
      { id: "chart", title: "Strategy Signals Chart", type: "CHART", colSpan: 2, rowSpan: 2, visible: true },
      { id: "trades", title: "Backtest Performance Log", type: "TRADES", colSpan: 2, rowSpan: 1, visible: true },
    ],
  },
];

interface WorkspaceState {
  workspaces: WorkspaceLayout[];
  activeWorkspaceId: string;
  activeSymbol: string;
  activeTimeframe: string;
  activeStrategyId: string | null;
  dateRange: { start: string; end: string };
  isEditMode: boolean;

  // Actions
  setActiveWorkspace: (id: string) => void;
  setActiveSymbol: (symbol: string) => void;
  setActiveTimeframe: (tf: string) => void;
  setActiveStrategyId: (id: string | null) => void;
  setDateRange: (range: { start: string; end: string }) => void;
  toggleEditMode: () => void;

  // Layout Actions
  saveCurrentAsCustom: (name: string, description?: string) => void;
  deleteWorkspace: (id: string) => void;
  reorderWidgets: (workspaceId: string, widgets: WidgetConfig[]) => void;
  toggleWidgetVisibility: (workspaceId: string, widgetId: string) => void;
  exportLayoutJSON: (workspaceId: string) => string;
  importLayoutJSON: (jsonString: string) => boolean;
  resetToDefaults: () => void;
}

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set, get) => ({
      workspaces: DEFAULT_PRESETS,
      activeWorkspaceId: "trading-default",
      activeSymbol: "RELIANCE.NS",
      activeTimeframe: "1d",
      activeStrategyId: null,
      dateRange: { start: "2026-08-01", end: "2026-08-06" },
      isEditMode: false,

      setActiveWorkspace: (id: string) => {
        const ws = get().workspaces.find((w) => w.id === id);
        if (ws) {
          set({
            activeWorkspaceId: id,
            activeSymbol: ws.activeSymbol || get().activeSymbol,
            activeTimeframe: ws.activeTimeframe || get().activeTimeframe,
          });
        }
      },
      setActiveSymbol: (symbol) => set({ activeSymbol: symbol }),
      setActiveTimeframe: (tf) => set({ activeTimeframe: tf }),
      setActiveStrategyId: (id) => set({ activeStrategyId: id }),
      setDateRange: (range) => set({ dateRange: range }),
      toggleEditMode: () => set((state) => ({ isEditMode: !state.isEditMode })),

      saveCurrentAsCustom: (name: string, description = "Custom institutional layout") => {
        const current = get().workspaces.find((w) => w.id === get().activeWorkspaceId) || DEFAULT_PRESETS[0];
        const newWs: WorkspaceLayout = {
          ...current,
          id: `custom-${Date.now()}`,
          name,
          description,
          isPreset: false,
          activeSymbol: get().activeSymbol,
          activeTimeframe: get().activeTimeframe,
          updatedAt: new Date().toISOString(),
        };
        set((state) => ({
          workspaces: [...state.workspaces, newWs],
          activeWorkspaceId: newWs.id,
        }));
      },

      deleteWorkspace: (id: string) => {
        const target = get().workspaces.find((w) => w.id === id);
        if (target?.isPreset) return; // Prevent deleting default presets

        set((state) => {
          const nextWorkspaces = state.workspaces.filter((w) => w.id !== id);
          return {
            workspaces: nextWorkspaces,
            activeWorkspaceId: state.activeWorkspaceId === id ? DEFAULT_PRESETS[0].id : state.activeWorkspaceId,
          };
        });
      },

      reorderWidgets: (workspaceId: string, widgets: WidgetConfig[]) => {
        set((state) => ({
          workspaces: state.workspaces.map((w) => (w.id === workspaceId ? { ...w, widgets, updatedAt: new Date().toISOString() } : w)),
        }));
      },

      toggleWidgetVisibility: (workspaceId: string, widgetId: string) => {
        set((state) => ({
          workspaces: state.workspaces.map((w) => {
            if (w.id !== workspaceId) return w;
            const updatedWidgets = w.widgets.map((widget) => (widget.id === widgetId ? { ...widget, visible: !widget.visible } : widget));
            return { ...w, widgets: updatedWidgets, updatedAt: new Date().toISOString() };
          }),
        }));
      },

      exportLayoutJSON: (workspaceId: string) => {
        const ws = get().workspaces.find((w) => w.id === workspaceId);
        return JSON.stringify(ws || {}, null, 2);
      },

      importLayoutJSON: (jsonString: string) => {
        try {
          const parsed = JSON.parse(jsonString) as WorkspaceLayout;
          if (!parsed.name || !Array.isArray(parsed.widgets)) return false;

          const imported: WorkspaceLayout = {
            ...parsed,
            id: `imported-${Date.now()}`,
            isPreset: false,
            updatedAt: new Date().toISOString(),
          };

          set((state) => ({
            workspaces: [...state.workspaces, imported],
            activeWorkspaceId: imported.id,
          }));
          return true;
        } catch {
          return false;
        }
      },

      resetToDefaults: () => {
        set({
          workspaces: DEFAULT_PRESETS,
          activeWorkspaceId: "trading-default",
        });
      },
    }),
    {
      name: "tradebot-workspace-storage",
      partialize: (state) => ({
        workspaces: state.workspaces,
        activeWorkspaceId: state.activeWorkspaceId,
        activeSymbol: state.activeSymbol,
        activeTimeframe: state.activeTimeframe,
      }),
    }
  )
);
