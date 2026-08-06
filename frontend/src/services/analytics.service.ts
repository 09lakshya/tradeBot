import { apiFetch } from "./client";

export const analyticsService = {
  getPerformanceSummary: () => apiFetch<any>("/api/v1/analytics/performance"),
  getEquityCurve: () => apiFetch<any[]>("/api/v1/analytics/equity-curve"),
  getTradeJournal: (limit: number = 50) =>
    apiFetch<any[]>(`/api/v1/analytics/journal?limit=${limit}`),
  getCostProfile: () => apiFetch<any>("/api/v1/analytics/cost-profile"),
};
