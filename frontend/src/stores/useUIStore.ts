import { create } from "zustand";
import { persist } from "zustand/middleware";

export type ThemeMode = "dark" | "light" | "high-contrast";
export type AccentColor = "emerald" | "blue" | "violet" | "amber" | "crimson";

interface UIState {
  sidebarCollapsed: boolean;
  activeModal: string | null;
  theme: ThemeMode;
  accentColor: AccentColor;

  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  openModal: (modalName: string) => void;
  closeModal: () => void;
  setTheme: (theme: ThemeMode) => void;
  setAccentColor: (color: AccentColor) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      activeModal: null,
      theme: "dark",
      accentColor: "emerald",

      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
      openModal: (modalName) => set({ activeModal: modalName }),
      closeModal: () => set({ activeModal: null }),
      setTheme: (theme) => set({ theme }),
      setAccentColor: (accentColor) => set({ accentColor }),
    }),
    {
      name: "tradebot-ui-settings",
      partialize: (state) => ({
        sidebarCollapsed: state.sidebarCollapsed,
        theme: state.theme,
        accentColor: state.accentColor,
      }),
    }
  )
);
