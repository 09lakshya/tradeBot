import { apiFetch } from "./client";

export interface OrderPayload {
  symbol: string;
  side: "BUY" | "SELL";
  order_type: "MARKET" | "LIMIT" | "STOP_LOSS";
  quantity: number;
  price?: number;
  strategy_id?: string;
}

export const tradingService = {
  getPortfolio: () => apiFetch<any>("/api/v1/trading/portfolio"),
  getPositions: () => apiFetch<any[]>("/api/v1/trading/positions"),
  getOrders: (status?: string) => {
    const params = status ? `?status=${status}` : "";
    return apiFetch<any[]>(`/api/v1/trading/orders${params}`);
  },
  placeOrder: (order: OrderPayload) =>
    apiFetch<any>("/api/v1/trading/orders", {
      method: "POST",
      body: JSON.stringify(order),
    }),
  cancelOrder: (orderId: string) =>
    apiFetch<any>(`/api/v1/trading/orders/${orderId}/cancel`, {
      method: "POST",
    }),
  getCashLedger: () => apiFetch<any>("/api/v1/trading/ledger"),
};
