import { apiFetch } from "./client";
import type {
  DashboardReplayResponse,
  OperationalAlert,
  PortfolioDailySnapshot,
  ReadinessAssessment,
  ReplaySessionState,
  ResearchExperiment,
  ResearchNote,
  SchedulerConfigSchema,
  SchedulerStatusResponse,
  StrategyHealthReport,
  TradeExplanation,
} from "@/types";

export const operationsService = {
  // Scheduler
  getSchedulerStatus: () =>
    apiFetch<SchedulerStatusResponse>("/api/v1/operations/scheduler/status"),

  controlScheduler: (action: string, manual_mode_override: boolean = false) =>
    apiFetch<SchedulerStatusResponse>("/api/v1/operations/scheduler/control", {
      method: "POST",
      body: JSON.stringify({ action, manual_mode_override }),
    }),

  configureScheduler: (config: Partial<SchedulerConfigSchema>) =>
    apiFetch<SchedulerConfigSchema>("/api/v1/operations/scheduler/config", {
      method: "POST",
      body: JSON.stringify(config),
    }),

  // Snapshots
  createSnapshot: () =>
    apiFetch<PortfolioDailySnapshot>("/api/v1/operations/snapshots/create", {
      method: "POST",
    }),

  listSnapshots: (startDate?: string, endDate?: string, limit: number = 30) => {
    const params = new URLSearchParams();
    if (startDate) params.append("start_date", startDate);
    if (endDate) params.append("end_date", endDate);
    params.append("limit", limit.toString());
    return apiFetch<{ total_snapshots: number; snapshots: PortfolioDailySnapshot[] }>(
      `/api/v1/operations/snapshots?${params.toString()}`
    );
  },

  getSnapshot: (date: string) =>
    apiFetch<PortfolioDailySnapshot>(`/api/v1/operations/snapshots/${date}`),

  // Reports
  generateReport: (reportType: string, startDate: string, endDate: string, format: string = "json") =>
    apiFetch<any>("/api/v1/operations/reports/generate", {
      method: "POST",
      body: JSON.stringify({
        report_type: reportType,
        start_date: startDate,
        end_date: endDate,
        export_format: format,
      }),
    }),

  // Explainability
  listExplanations: (strategyId?: string, symbol?: string) => {
    const params = new URLSearchParams();
    if (strategyId) params.append("strategy_id", strategyId);
    if (symbol) params.append("symbol", symbol);
    return apiFetch<TradeExplanation[]>(`/api/v1/operations/explainability?${params.toString()}`);
  },

  getTradeExplanation: (tradeId: string) =>
    apiFetch<TradeExplanation>(`/api/v1/operations/explainability/trade/${tradeId}`),

  // Replay
  createReplaySession: (date: string = "2026-08-04") =>
    apiFetch<ReplaySessionState>(`/api/v1/operations/replay/create?date=${date}`, {
      method: "POST",
    }),

  executeReplayAction: (sessionId: string, action: string, targetStep?: number) =>
    apiFetch<any>(`/api/v1/operations/replay/${sessionId}/action`, {
      method: "POST",
      body: JSON.stringify({ action, target_step: targetStep }),
    }),

  getDashboardReplay: (days: number = 30) =>
    apiFetch<DashboardReplayResponse>(`/api/v1/operations/dashboard/replay?days=${days}`),

  // Health
  listHealthReports: () =>
    apiFetch<StrategyHealthReport[]>("/api/v1/operations/health"),

  evaluateStrategyHealth: (strategyId: string = "trend_following_v1") =>
    apiFetch<StrategyHealthReport>(`/api/v1/operations/health/evaluate?strategy_id=${strategyId}`, {
      method: "POST",
    }),

  // Experiments
  listExperiments: () =>
    apiFetch<ResearchExperiment[]>("/api/v1/operations/experiments"),

  createExperiment: (data: { name: string; experiment_type: string; config: any; description?: string }) =>
    apiFetch<ResearchExperiment>("/api/v1/operations/experiments", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  runExperiment: (expId: string) =>
    apiFetch<ResearchExperiment>(`/api/v1/operations/experiments/${expId}/run`, {
      method: "POST",
    }),

  // Readiness
  assessReadiness: () =>
    apiFetch<ReadinessAssessment>("/api/v1/operations/readiness/assess", {
      method: "POST",
    }),

  // Alerts
  listAlerts: () => apiFetch<OperationalAlert[]>("/api/v1/operations/alerts"),

  resolveAlert: (alertId: string) =>
    apiFetch<OperationalAlert>(`/api/v1/operations/alerts/${alertId}/resolve`, {
      method: "POST",
    }),

  // Notes
  listNotes: (entityType?: string, entityId?: string) => {
    const params = new URLSearchParams();
    if (entityType) params.append("entity_type", entityType);
    if (entityId) params.append("entity_id", entityId);
    return apiFetch<ResearchNote[]>(`/api/v1/operations/notes?${params.toString()}`);
  },

  createNote: (data: { entity_type: string; entity_id: string; author: string; title: string; content_markdown: string; tags?: string[] }) =>
    apiFetch<ResearchNote>("/api/v1/operations/notes", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};
