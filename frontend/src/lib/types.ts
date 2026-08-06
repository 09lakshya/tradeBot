export interface PortfolioSummary {
  portfolio_id: string;
  portfolio_name: string;
  base_currency: string;
  net_liquidation_value: number;
  gross_position_value: number;
  cash_balance: number;
  locked_buying_power: number;
  unrealized_pnl: number;
  realized_pnl: number;
  updated_at: string;
}

export interface GrossNetPerformance {
  gross: {
    total_return_pct: number;
    sharpe_ratio: number;
    max_drawdown_pct: number;
    win_rate_pct: number;
    profit_factor: number;
    todays_pnl: number;
  };
  net: {
    total_return_pct: number;
    sharpe_ratio: number;
    max_drawdown_pct: number;
    win_rate_pct: number;
    profit_factor: number;
    todays_pnl: number;
  };
  total_costs_incurred: number;
}

export interface EquityCurvePoint {
  timestamp: string;
  gross_equity: number;
  net_equity: number;
}

export interface EquityCurveData {
  portfolio_id: string;
  points: EquityCurvePoint[];
}

export interface DrawdownPoint {
  timestamp: string;
  drawdown_pct: number;
  drawdown_val: number;
}

export interface DrawdownData {
  portfolio_id: string;
  points: DrawdownPoint[];
}

export interface RiskAnalytics {
  portfolio_id: string;
  cash_utilization_pct: number;
  sector_exposure: Record<string, number>;
  symbol_exposure: Record<string, number>;
  strategy_exposure: Record<string, number>;
  concentration_hhi: number;
}

export interface Position {
  id: string;
  portfolio_id: string;
  instrument_id: string;
  symbol: string;
  side: "LONG" | "SHORT";
  quantity: number;
  average_entry_price: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct?: number;
  sector?: string;
  status: string;
  updated_at: string;
}

export interface Trade {
  trade_id: string;
  portfolio_id: string;
  strategy_id: string;
  symbol: string;
  side: "BUY" | "SELL";
  quantity: number;
  entry_price: number;
  exit_price?: number;
  realized_pnl: number;
  execution_time: string;
  status: string;
  reason?: string;
}

export interface StrategyHealth {
  strategy_id: string;
  health_score: number;
  win_rate: number;
  profit_factor: number;
  sharpe_ratio: number;
  max_drawdown: number;
  status: "HEALTHY" | "DEGRADED" | "TRIPPED" | "UNKNOWN";
  degradation_detected: boolean;
  notes?: string;
}

export interface SchedulerStatus {
  is_running: boolean;
  is_paused: boolean;
  mode: string;
  last_run_at: string | null;
  next_run_at: string | null;
  interval_seconds: number;
  active_tasks: number;
}

export interface TradingDayInfo {
  exchange: "NSE" | "BSE";
  day: string;
  is_trading_day: boolean;
  session_type: string;
  open_time: string | null;
  close_time: string | null;
}

export interface PortfolioAccount {
  id: string;
  name: string;
  mode: string;
  initial_capital: number;
  base_currency: string;
}

export interface DailyReturnPoint {
  date: string;
  gross_return_pct: number;
  net_return_pct: number;
  gross_pnl: number;
  net_pnl: number;
}

export interface MonthlyReturnPoint {
  month: string;
  year: number;
  net_return_pct: number;
  gross_return_pct: number;
  net_pnl: number;
}
