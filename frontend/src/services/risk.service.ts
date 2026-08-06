import { apiFetch } from "./client";

export const riskService = {
  getRiskMetrics: () => apiFetch<any>("/api/v1/risk/metrics"),
  getCircuitBreakers: () => apiFetch<any[]>("/api/v1/risk/circuit-breakers"),
  getKillSwitchStatus: () => apiFetch<{ is_engaged: boolean }>("/api/v1/risk/kill-switch"),
  engageKillSwitch: (reason: string) =>
    apiFetch<any>("/api/v1/risk/kill-switch/engage", {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  disengageKillSwitch: () =>
    apiFetch<any>("/api/v1/risk/kill-switch/disengage", {
      method: "POST",
    }),
};
