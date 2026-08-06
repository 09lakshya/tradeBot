import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Formats numbers into Indian Rupees currency string (e.g. ₹1,04,60,000.00) */
export function formatINR(val: number | null | undefined): string {
  if (val === null || val === undefined || isNaN(val)) return "₹0.00";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(val);
}

export const formatCurrency = formatINR;

/** Formats percentage numbers (e.g. 0.046 -> 4.60%) */
export function formatPercent(val: number | null | undefined, digits: number = 2): string {
  if (val === null || val === undefined || isNaN(val)) return "0.00%";
  const pct = val * 100;
  const prefix = pct > 0 ? "+" : "";
  return `${prefix}${pct.toFixed(digits)}%`;
}

/** Formats ISO timestamp into local readable date-time */
export function formatDate(isoStr: string | null | undefined): string {
  if (!isoStr) return "N/A";
  try {
    const d = new Date(isoStr);
    return d.toLocaleString("en-IN", {
      dateStyle: "short",
      timeStyle: "medium",
    });
  } catch {
    return isoStr;
  }
}
