import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { AppProviders } from "@/providers/app-providers";
import { Header } from "@/components/navigation/Header";
import { Sidebar } from "@/components/navigation/Sidebar";
import { FooterStatusBar } from "@/components/navigation/FooterStatusBar";
import { CommandPalette } from "@/components/navigation/CommandPalette";

export const metadata: Metadata = {
  title: "Trade Bot — Institutional AI Quantitative Trading Terminal",
  description: "Autonomous paper trading operations, trade explainability, decision replay & live readiness assessment dashboard.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="dark scroll-smooth">
      <body className="bg-slate-950 text-slate-100 font-sans antialiased min-h-screen flex flex-col selection:bg-emerald-500/30 selection:text-emerald-200">
        <AppProviders>
          <Header />
          <div className="flex flex-1 relative">
            <Sidebar />
            <main className="flex-1 p-4 pb-12 overflow-y-auto min-w-0">
              {children}
            </main>
          </div>
          <FooterStatusBar />
          <CommandPalette />
        </AppProviders>
      </body>
    </html>
  );
}
