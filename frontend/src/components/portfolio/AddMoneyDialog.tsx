"use client";

import React, { useState } from "react";
import { IndianRupee, Loader2, X } from "lucide-react";
import { tradingService } from "@/services/trading.service";
import { formatINR } from "@/lib/utils";

interface AddMoneyDialogProps {
  /** Null when no wallet exists yet: the first deposit has to create one. */
  portfolioId: string | null;
  currentBalance: number;
  onClose: () => void;
  /** Fired after the credit lands so the caller can refetch. */
  onFunded: () => void;
}

const QUICK_AMOUNTS = [10000, 50000, 100000, 500000];

export function AddMoneyDialog({
  portfolioId,
  currentBalance,
  onClose,
  onFunded,
}: AddMoneyDialogProps) {
  const [amount, setAmount] = useState<string>("");
  const [name, setName] = useState<string>("My Portfolio");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parsed = Number(amount);
  const isValid = amount.trim() !== "" && Number.isFinite(parsed) && parsed > 0;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid || isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    try {
      if (portfolioId) {
        await tradingService.deposit(parsed, "Manual deposit");
      } else {
        await tradingService.createPortfolio(name.trim() || "My Portfolio", parsed);
      }
      onFunded();
      onClose();
    } catch (err: any) {
      setError(err?.message ?? "Could not add money. Is the API running?");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between border-b border-slate-800 pb-3">
          <div>
            <h2 className="text-sm font-bold font-mono text-slate-100 flex items-center gap-2">
              <IndianRupee className="w-4 h-4 text-emerald-400" />
              {portfolioId ? "Add Money" : "Open Wallet & Add Money"}
            </h2>
            <p className="text-[11px] text-slate-500 font-mono mt-1">
              {portfolioId
                ? `Current balance ${formatINR(currentBalance)} · paper trading only`
                : "Creates your paper trading wallet with this opening balance"}
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="text-slate-500 hover:text-slate-200 p-1"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {!portfolioId && (
            <div>
              <label htmlFor="wallet-name" className="block text-[11px] font-mono text-slate-400 mb-1">
                Wallet name
              </label>
              <input
                id="wallet-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={100}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-100 font-mono outline-none focus:border-emerald-500"
              />
            </div>
          )}

          <div>
            <label htmlFor="amount" className="block text-[11px] font-mono text-slate-400 mb-1">
              Amount (₹)
            </label>
            <input
              id="amount"
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              autoFocus
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="50000"
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-lg text-slate-100 font-mono outline-none focus:border-emerald-500"
            />
            <div className="flex flex-wrap gap-2 mt-2">
              {QUICK_AMOUNTS.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => setAmount(String(q))}
                  className="px-2 py-1 rounded border border-slate-700 bg-slate-950 text-[11px] font-mono text-slate-300 hover:border-emerald-500 hover:text-emerald-300"
                >
                  +{formatINR(q)}
                </button>
              ))}
            </div>
          </div>

          {isValid && portfolioId && (
            <p className="text-[11px] font-mono text-slate-400">
              New balance:{" "}
              <span className="text-emerald-400 font-bold">
                {formatINR(currentBalance + parsed)}
              </span>
            </p>
          )}

          {error && (
            <p className="text-[11px] font-mono text-rose-400 bg-rose-500/10 border border-rose-500/30 rounded px-2 py-1.5">
              {error}
            </p>
          )}

          <div className="flex items-center justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-2 rounded-lg text-xs font-mono text-slate-400 hover:text-slate-200"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!isValid || isSubmitting}
              className="px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-bold font-mono flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {isSubmitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              {portfolioId ? "Add Money" : "Create & Fund"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
