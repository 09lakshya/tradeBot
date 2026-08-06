import { create } from "zustand";

interface CommandState {
  isOpen: boolean;
  query: string;
  openCommandPalette: () => void;
  closeCommandPalette: () => void;
  toggleCommandPalette: () => void;
  setQuery: (q: string) => void;
}

export const useCommandStore = create<CommandState>((set) => ({
  isOpen: false,
  query: "",
  openCommandPalette: () => set({ isOpen: true }),
  closeCommandPalette: () => set({ isOpen: false, query: "" }),
  toggleCommandPalette: () => set((state) => ({ isOpen: !state.isOpen, query: "" })),
  setQuery: (q) => set({ query: q }),
}));
