import { create } from "zustand";

export type NotificationCategory =
  | "Orders"
  | "Risk"
  | "Strategies"
  | "Portfolio"
  | "Operations"
  | "System"
  | "Market"
  | "Alerts";

export type NotificationSeverity = "info" | "success" | "warning" | "error" | "critical";

export interface ToastNotification {
  id: string;
  category: NotificationCategory;
  severity: NotificationSeverity;
  type?: "info" | "success" | "warning" | "error"; // Backwards compatibility
  title: string;
  message: string;
  timestamp: string;
  read: boolean;
  archived: boolean;
}

interface NotificationState {
  notifications: ToastNotification[];
  isCenterOpen: boolean;

  // Actions
  toggleNotificationCenter: () => void;
  setCenterOpen: (open: boolean) => void;
  addNotification: (
    notification: Omit<ToastNotification, "id" | "timestamp" | "read" | "archived">
  ) => void;
  markAsRead: (id: string) => void;
  markAllAsRead: () => void;
  archiveNotification: (id: string) => void;
  clearAll: () => void;
}

// Seeded empty: the history is built from real events via addNotification().
// This used to ship four fabricated entries ("BUY 50 RELIANCE @ ₹2,475 filled",
// a VaR breach, a strategy signal) that appeared on a system with no trades.
const INITIAL_NOTIFICATIONS: ToastNotification[] = [];

export const useNotificationStore = create<NotificationState>((set) => ({
  notifications: INITIAL_NOTIFICATIONS,
  isCenterOpen: false,

  toggleNotificationCenter: () => set((state) => ({ isCenterOpen: !state.isCenterOpen })),
  setCenterOpen: (open) => set({ isCenterOpen: open }),

  addNotification: (n) => {
    const id = `notif-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`;
    const timestamp = new Date().toLocaleTimeString();
    const newNotif: ToastNotification = {
      ...n,
      id,
      timestamp,
      read: false,
      archived: false,
    };
    set((state) => ({ notifications: [newNotif, ...state.notifications] }));
  },

  markAsRead: (id) =>
    set((state) => ({
      notifications: state.notifications.map((n) => (n.id === id ? { ...n, read: true } : n)),
    })),

  markAllAsRead: () =>
    set((state) => ({
      notifications: state.notifications.map((n) => ({ ...n, read: true })),
    })),

  archiveNotification: (id) =>
    set((state) => ({
      notifications: state.notifications.map((n) => (n.id === id ? { ...n, archived: true } : n)),
    })),

  clearAll: () => set({ notifications: [] }),
}));
