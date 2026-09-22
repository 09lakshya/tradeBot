import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { AppProviders } from "@/providers/app-providers";
import { ClientLayoutShell } from "@/components/common/ClientLayoutShell";

export const metadata: Metadata = {
  title: "Trade Bot — Institutional AI Quantitative Trading Terminal",
  description: "Autonomous paper trading operations, trade explainability, decision replay & live readiness assessment dashboard.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="dark scroll-smooth">
      <body className="antialiased min-h-screen">
        <AppProviders>
          <ClientLayoutShell>{children}</ClientLayoutShell>
        </AppProviders>
      </body>
    </html>
  );
}
