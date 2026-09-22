"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useCommandStore } from "@/stores/useCommandStore";
import { useUIStore } from "@/stores/useUIStore";
import { useNotificationStore } from "@/stores/useNotificationStore";

export function useKeyboardShortcuts() {
  const router = useRouter();
  const { toggleCommandPalette, closeCommandPalette, isOpen: isCommandOpen } = useCommandStore();
  const { toggleSidebar, activeModal, closeModal, openModal } = useUIStore();
  const { setCenterOpen, isCenterOpen } = useNotificationStore();

  const [isHelpModalOpen, setIsHelpModalOpen] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Avoid intercepting shortcuts when typing inside form inputs
      const target = e.target as HTMLElement;
      const isInput =
        target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable;

      // Esc key - Close any active overlay
      if (e.key === "Escape") {
        if (isCommandOpen) closeCommandPalette();
        if (isCenterOpen) setCenterOpen(false);
        if (activeModal) closeModal();
        if (isHelpModalOpen) setIsHelpModalOpen(false);
        return;
      }

      // Ctrl+K or Cmd+K - Command Palette
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        toggleCommandPalette();
        return;
      }

      // Ctrl+B or Cmd+B - Toggle Sidebar
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        toggleSidebar();
        return;
      }

      // Ctrl+Shift+R - Quick Reset / Hard Refresh
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "r") {
        e.preventDefault();
        window.location.reload();
        return;
      }

      // '?' or Ctrl+/ - Toggle Keyboard Shortcut Legend Help
      if (!isInput && (e.key === "?" || ((e.ctrlKey || e.metaKey) && e.key === "/"))) {
        e.preventDefault();
        setIsHelpModalOpen((prev) => !prev);
        return;
      }

      // F1-F12 Navigation (Allowed unless in full typing mode)
      if (e.key.startsWith("F") && e.key.length <= 3) {
        switch (e.key) {
          case "F1":
            e.preventDefault();
            router.push("/");
            break;
          case "F2":
            e.preventDefault();
            router.push("/orders");
            break;
          case "F3":
            e.preventDefault();
            router.push("/positions");
            break;
          case "F4":
            e.preventDefault();
            router.push("/risk");
            break;
          case "F5":
            e.preventDefault();
            router.push("/strategies");
            break;
          case "F6":
            e.preventDefault();
            router.push("/portfolio");
            break;
          case "F7":
            e.preventDefault();
            router.push("/analytics");
            break;
          case "F8":
            e.preventDefault();
            router.push("/market-scanner");
            break;
          case "F9":
            e.preventDefault();
            router.push("/backtest");
            break;
          case "F10":
            e.preventDefault();
            router.push("/operations");
            break;
          case "F11":
            e.preventDefault();
            router.push("/explainability");
            break;
          case "F12":
            e.preventDefault();
            router.push("/settings");
            break;
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    router,
    toggleCommandPalette,
    closeCommandPalette,
    isCommandOpen,
    toggleSidebar,
    activeModal,
    closeModal,
    isCenterOpen,
    setCenterOpen,
    isHelpModalOpen,
  ]);

  return {
    isHelpModalOpen,
    setIsHelpModalOpen,
  };
}
