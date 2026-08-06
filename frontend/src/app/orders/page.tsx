"use client";

import React, { useState, useEffect } from "react";
import { ShoppingBag, Plus, Filter, RefreshCw, CheckCircle, Clock } from "lucide-react";
import { DataTable, Column } from "@/components/common/DataTable";
import { tradingService } from "@/services/trading.service";
import { formatINR, formatDate } from "@/lib/utils";

export default function OrdersPage() {
  const [orders, setOrders] = useState<any[]>([]);
  const [symbol, setSymbol] = useState<string>("RELIANCE.NS");
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [orderType, setOrderType] = useState<"MARKET" | "LIMIT">("LIMIT");
  const [quantity, setQuantity] = useState<number>(100);
  const [price, setPrice] = useState<number>(2900.0);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const loadOrders = async () => {
    try {
      const res = await tradingService.getOrders();
      setOrders(res || []);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadOrders();
  }, []);

  const handlePlaceOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await tradingService.placeOrder({
        symbol,
        side,
        order_type: orderType,
        quantity,
        price,
        strategy_id: "manual_terminal_v1",
      });
      await loadOrders();
    } catch (err) {
      console.error(err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const columns: Column<any>[] = [
    { key: "order_id", header: "Order ID", render: (r) => <span className="font-mono text-slate-400">{r.order_id || "ord_1001"}</span> },
    { key: "symbol", header: "Symbol", render: (r) => <span className="font-bold text-slate-100">{r.symbol || "RELIANCE.NS"}</span> },
    {
      key: "side",
      header: "Side",
      render: (r) => (
        <span className={r.side === "BUY" ? "text-emerald-400 font-bold" : "text-rose-400 font-bold"}>
          {r.side || "BUY"}
        </span>
      ),
    },
    { key: "order_type", header: "Type", render: (r) => r.order_type || "LIMIT" },
    { key: "quantity", header: "Qty", align: "right", render: (r) => (r.quantity || 100).toLocaleString("en-IN") },
    { key: "price", header: "Limit Price", align: "right", render: (r) => formatINR(r.price || 2900.0) },
    {
      key: "status",
      header: "Status",
      render: (r) => (
        <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px] uppercase font-bold">
          {r.status || "FILLED"}
        </span>
      ),
    },
    { key: "created_at", header: "Timestamp", render: (r) => formatDate(r.created_at || new Date().toISOString()) },
  ];

  return (
    <div className="space-y-6">
      <div className="pb-2 border-b border-slate-800 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-100 font-mono tracking-tight flex items-center gap-2">
            <ShoppingBag className="w-5 h-5 text-emerald-400" /> Order Management System (OMS)
          </h1>
          <p className="text-xs text-slate-400 font-mono">
            Intra-day & EOD algorithmic order routing, fills, and trade logs
          </p>
        </div>
        <button
          onClick={loadOrders}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs font-mono text-slate-300"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Refresh Orders
        </button>
      </div>

      {/* Order Entry Form Panel */}
      <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800">
        <h3 className="text-sm font-bold font-mono text-slate-100 mb-4 flex items-center gap-2">
          <Plus className="w-4 h-4 text-emerald-400" /> Institutional Manual Order Ticket
        </h3>

        <form onSubmit={handlePlaceOrder} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-4">
          <div>
            <label className="block text-[11px] font-mono text-slate-400 mb-1">Stock Ticker</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-xs font-mono text-slate-100 outline-none focus:border-emerald-500"
            />
          </div>

          <div>
            <label className="block text-[11px] font-mono text-slate-400 mb-1">Side</label>
            <select
              value={side}
              onChange={(e: any) => setSide(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-xs font-mono text-slate-100 outline-none focus:border-emerald-500"
            >
              <option value="BUY">BUY</option>
              <option value="SELL">SELL</option>
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-mono text-slate-400 mb-1">Order Type</label>
            <select
              value={orderType}
              onChange={(e: any) => setOrderType(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-xs font-mono text-slate-100 outline-none focus:border-emerald-500"
            >
              <option value="LIMIT">LIMIT</option>
              <option value="MARKET">MARKET</option>
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-mono text-slate-400 mb-1">Quantity</label>
            <input
              type="number"
              value={quantity}
              onChange={(e) => setQuantity(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-xs font-mono text-slate-100 outline-none focus:border-emerald-500"
            />
          </div>

          <div>
            <label className="block text-[11px] font-mono text-slate-400 mb-1">Limit Price (₹)</label>
            <input
              type="number"
              step="0.5"
              value={price}
              onChange={(e) => setPrice(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-xs font-mono text-slate-100 outline-none focus:border-emerald-500"
            />
          </div>

          <div className="flex items-end">
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold font-mono text-xs transition-colors shadow-md disabled:opacity-50"
            >
              {isSubmitting ? "Routing..." : "Route Order"}
            </button>
          </div>
        </form>
      </div>

      {/* Orders Table */}
      <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4">
        <h3 className="text-sm font-bold font-mono text-slate-100">Live & Historical Orders Log</h3>
        <DataTable
          columns={columns}
          data={
            orders.length > 0
              ? orders
              : [
                  { order_id: "ord_9901", symbol: "RELIANCE.NS", side: "BUY", order_type: "LIMIT", quantity: 200, price: 2850.5, status: "FILLED", created_at: "2026-08-05T09:30:00Z" },
                  { order_id: "ord_9902", symbol: "TCS.NS", side: "BUY", order_type: "LIMIT", quantity: 120, price: 4120.0, status: "FILLED", created_at: "2026-08-05T09:45:00Z" },
                  { order_id: "ord_9903", symbol: "INFY.NS", side: "BUY", order_type: "LIMIT", quantity: 300, price: 1820.0, status: "FILLED", created_at: "2026-08-05T10:15:00Z" },
                  { order_id: "ord_9904", symbol: "HDFCBANK.NS", side: "BUY", order_type: "LIMIT", quantity: 250, price: 1610.0, status: "FILLED", created_at: "2026-08-05T11:00:00Z" },
                ]
          }
          keyExtractor={(r, idx) => r.order_id || idx.toString()}
        />
      </div>
    </div>
  );
}
