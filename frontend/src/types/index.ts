export type OperationalMode = "autonomous" | "manual_override" | "paused" | "stopped";
export type AlertSeverity = "info" | "warning" | "error" | "critical";
export type ReadinessStatus = "READY FOR LIVE PILOT" | "NEEDS CONTINUOUS PAPER TRADING" | "NOT READY FOR LIVE DEPLOYMENT";
export type ExperimentStatus = "pending" | "running" | "completed" | "failed";

export interface SchedulerConfigSchema {
  interval_seconds: number;
  auto_start_pre_market: boolean;
  auto_stop_post_market: boolean;
  run_on_weekends: boolean;
  market_open_utc_hour: number;
  market_open_utc_minute: number;
  market_close_utc_hour: number;
  market_close_utc_minute: number;
}

export interface SchedulerStatusResponse {
  mode: OperationalMode;
  is_running: boolean;
  is_market_open: boolean;
  is_weekend: boolean;
  is_holiday: boolean;
  interval_seconds: number;
  last_run_timestamp?: string;
  next_run_timestamp?: string;
  total_execution_cycles: number;
  recent_execution_history: Array<Record<string, any>>;
}

export interface PortfolioDailySnapshot {
  snapshot_id: string;
  date: string;
  portfolio_value: number;
  cash_balance: number;
  invested_capital: number;
  unrealized_pnl: number;
  realized_pnl: number;
  gross_return: number;
  net_return: number;
  drawdown: number;
  open_positions_count: number;
  closed_trades_count: number;
  open_positions: Array<Record<string, any>>;
  closed_trades: Array<Record<string, any>>;
  risk_metrics: Record<string, number>;
  strategy_allocation: Record<string, number>;
  exposure: Record<string, number>;
  cost_breakdown: Record<string, number>;
  timestamp: string;
}

export interface SignalReason {
  indicators_involved: string[];
  indicator_values: Record<string, number>;
  confidence_score: number;
  rationale: string;
}

export interface RiskReason {
  approved: boolean;
  rules_evaluated: string[];
  violated_rules: string[];
  rationale: string;
}

export interface PortfolioReason {
  accepted: boolean;
  position_sizing_selected: number;
  sizing_rationale: string;
  allocation_weight: number;
}

export interface ExecutionReason {
  executed: boolean;
  fill_price: number;
  slippage: number;
  commission: number;
  rationale: string;
}

export interface TradeExplanation {
  explanation_id: string;
  trade_id: string;
  order_id?: string;
  strategy_id: string;
  symbol: string;
  side: "BUY" | "SELL";
  timestamp: string;
  signal_reason: SignalReason;
  risk_reason: RiskReason;
  portfolio_reason: PortfolioReason;
  execution_reason: ExecutionReason;
  exit_reason?: string;
  narrative: string;
}

export interface StrategyHealthReport {
  strategy_id: string;
  win_rate: number;
  baseline_win_rate: number;
  win_rate_drift: number;
  profit_factor: number;
  baseline_profit_factor: number;
  profit_factor_drift: number;
  sharpe_ratio: number;
  baseline_sharpe: number;
  sharpe_drift: number;
  current_drawdown: number;
  max_drawdown_increase: number;
  signal_frequency_per_day: number;
  trade_frequency_per_day: number;
  regime_performance: Record<string, number>;
  recent_pnl_30d: number;
  is_degraded: boolean;
  degradation_reasons: string[];
  evaluated_at: string;
}

export interface PillarScore {
  name: string;
  score: number;
  weight: number;
  weighted_score: number;
  details: string;
}

export interface ReadinessAssessment {
  assessment_id: string;
  overall_score: number;
  status: ReadinessStatus;
  pillars: PillarScore[];
  passed_criteria_count: number;
  total_criteria_count: number;
  recommendations: string[];
  evaluated_at: string;
}

export interface OperationalAlert {
  alert_id: string;
  severity: AlertSeverity;
  alert_type: string;
  title: string;
  message: string;
  details: Record<string, any>;
  resolved: boolean;
  created_at: string;
  resolved_at?: string;
}

export interface ReplayStep {
  step_number: number;
  timestamp: string;
  market_prices: Record<string, number>;
  signals_generated: Array<Record<string, any>>;
  portfolio_decisions: Array<Record<string, any>>;
  risk_evaluations: Array<Record<string, any>>;
  orders_issued: Array<Record<string, any>>;
  positions_state: Array<Record<string, any>>;
  portfolio_value: number;
  cash_balance: number;
}

export interface ReplaySessionState {
  session_id: string;
  date: string;
  current_step: number;
  total_steps: number;
  is_playing: boolean;
  speed_multiplier: number;
  steps: ReplayStep[];
}

export interface DashboardReplayResponse {
  equity_curve: Array<{ date: string; equity: number }>;
  capital_deployment: Array<{ date: string; cash: number; invested: number }>;
  trade_sequence: Array<Record<string, any>>;
  position_history: Array<Record<string, any>>;
  cash_movement: Array<{ date: string; cash: number; delta: number }>;
  risk_evolution: Array<{ date: string; var_95: number; leverage: number }>;
  cost_accumulation: Array<{ date: string; cumulative_costs: number }>;
  gross_vs_net_equity: Array<{ date: string; gross_equity: number; net_equity: number }>;
}

export interface ResearchExperiment {
  experiment_id: string;
  name: string;
  description: string;
  experiment_type: string;
  status: ExperimentStatus;
  config: Record<string, any>;
  baseline_results?: Record<string, any>;
  variant_results: Record<string, any>;
  notes: string[];
  created_at: string;
  completed_at?: string;
}

export interface ResearchNote {
  note_id: string;
  entity_type: string;
  entity_id: string;
  author: string;
  title: string;
  content_markdown: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}
