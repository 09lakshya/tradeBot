import { apiFetch } from "./client";

export const marketDataService = {
  getInstruments: () => apiFetch<any[]>("/api/v1/market-data/instruments"),
  getCandles: (symbol: string, timeframe: string = "1d", limit: number = 100) =>
    apiFetch<any[]>(
      `/api/v1/market-data/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}`
    ),
  getTicker: (symbol: string) =>
    apiFetch<any>(`/api/v1/market-data/ticker?symbol=${encodeURIComponent(symbol)}`),
};
