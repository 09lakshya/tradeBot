import { create } from "zustand";

export interface ToastNotification {
  id: string;
  type: "info" | "success" | "warning" | "error";
  title: string;
  message: string;
  timestamp: string;
}

interface NotificationState {
  toasts: ToastNotification[];
  addToast: (toast: Omit<ToastNotification, "id" | "timestamp">) => void;
  removeToast: (id: string) => void;
  clearAll: () => void;
}

export const useNotificationStore = create<NotificationState>((set) => ({
  toasts: [],
  addToast: (toast) => {
    const id = Math.random().toString(36).substring(2, 9);
    const timestamp = new Date().toLocaleTimeString();
    const newToast: ToastNotification = { ...toast, id, timestamp };
    set((state) => ({ toasts: [newToast, ...state.toasts].slice(0, 10) }));
  },
  removeToast: (id) =>
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
  clearAll: () => set({ toasts: [] }),
}));
