"use client";

import React from "react";
import { Header } from "@/components/navigation/Header";
import { Sidebar } from "@/components/navigation/Sidebar";
import { FooterStatusBar } from "@/components/navigation/FooterStatusBar";
import { CommandPalette } from "@/components/navigation/CommandPalette";
import { NotificationCenter } from "@/components/navigation/NotificationCenter";
import { OfflineBanner } from "@/components/common/OfflineBanner";
import { ShortcutHelpModal } from "@/components/common/ShortcutHelpModal";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";

export function ClientLayoutShell({ children }: { children: React.ReactNode }) {
  const { isHelpModalOpen, setIsHelpModalOpen } = useKeyboardShortcuts();

  return (
    <div className="min-h-screen flex flex-col bg-slate-950 text-slate-100 selection:bg-emerald-500/30 selection:text-emerald-200">
      <OfflineBanner />
      <Header />
      <div className="flex flex-1 relative min-h-0">
        <Sidebar />
        <main className="flex-1 p-4 pb-12 overflow-y-auto min-w-0">
          <ErrorBoundary fallbackTitle="Page Execution Exception">
            {children}
          </ErrorBoundary>
        </main>
      </div>
      <FooterStatusBar />
      <CommandPalette />
      <NotificationCenter />
      <ShortcutHelpModal
        isOpen={isHelpModalOpen}
        onClose={() => setIsHelpModalOpen(false)}
      />
    </div>
  );
}
