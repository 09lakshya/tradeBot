import { apiFetch } from "./client";

export interface OrderPayload {
  symbol: string;
  side: "BUY" | "SELL";
  order_type: "MARKET" | "LIMIT" | "STOP_LOSS";
  quantity: number;
  price?: number;
  strategy_id?: string;
}

/** Portfolio-scoped endpoints need an id the pages don't carry, so resolve the
 *  active portfolio once and reuse it. Returns null when none exists yet (fresh
 *  database), which the callers below render as an empty list rather than an error. */
let activePortfolioId: string | null = null;

export async function getActivePortfolioId(): Promise<string | null> {
  if (activePortfolioId) return activePortfolioId;
  const portfolios = await apiFetch<any[]>("/api/v1/trading/portfolios");
  activePortfolioId = portfolios?.[0]?.id ?? null;
  return activePortfolioId;
}

/** Creating the first portfolio invalidates the "there is no wallet" answer. */
function setActivePortfolioId(id: string | null): void {
  activePortfolioId = id;
}

export const tradingService = {
  listPortfolios: () => apiFetch<any[]>("/api/v1/trading/portfolios"),

  /** Open a wallet. `initial_capital` is credited to the ledger as a deposit. */
  createPortfolio: async (name: string, initialCapital: number) => {
    const created = await apiFetch<any>("/api/v1/trading/portfolios", {
      method: "POST",
      body: JSON.stringify({ name, initial_capital: initialCapital }),
    });
    setActivePortfolioId(created?.id ?? null);
    return created;
  },

  /** Top up an existing wallet; recorded as its own ledger deposit. */
  deposit: async (amount: number, description?: string) => {
    const id = await getActivePortfolioId();
    if (!id) throw new Error("No portfolio exists yet.");
    return apiFetch<any>(`/api/v1/trading/portfolios/${id}/deposit`, {
      method: "POST",
      body: JSON.stringify({ amount, description }),
    });
  },
  getPortfolio: async () => {
    const id = await getActivePortfolioId();
    return id ? apiFetch<any>(`/api/v1/trading/portfolios/${id}`) : null;
  },
  getPositions: async () => {
    const id = await getActivePortfolioId();
    if (!id) return [];
    return apiFetch<any[]>(`/api/v1/trading/positions?portfolio_id=${id}`);
  },
  getOrders: (status?: string) => {
    // The API's status enum is lower-case; sending "FILLED" is a 422.
    const params = status ? `?status=${status.toLowerCase()}` : "";
    return apiFetch<any[]>(`/api/v1/trading/orders${params}`);
  },
  getTrades: () => apiFetch<any[]>("/api/v1/trading/orders?status=filled"),
  placeOrder: (order: OrderPayload) =>
    apiFetch<any>("/api/v1/trading/orders", {
      method: "POST",
      body: JSON.stringify(order),
    }),
  cancelOrder: (orderId: string) =>
    apiFetch<any>(`/api/v1/trading/orders/${orderId}/cancel`, {
      method: "POST",
    }),
  getCashLedger: async () => {
    const id = await getActivePortfolioId();
    if (!id) return null;
    return apiFetch<any>(`/api/v1/trading/ledger?portfolio_id=${id}`);
  },
};
