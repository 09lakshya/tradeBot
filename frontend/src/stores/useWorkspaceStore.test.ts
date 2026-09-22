import { describe, it, expect, beforeEach } from "vitest";
import { useWorkspaceStore } from "@/stores/useWorkspaceStore";

describe("useWorkspaceStore", () => {
  beforeEach(() => {
    useWorkspaceStore.getState().resetToDefaults();
  });

  it("should initialize with default workspace presets", () => {
    const { workspaces, activeWorkspaceId } = useWorkspaceStore.getState();
    expect(workspaces.length).toBeGreaterThanOrEqual(3);
    expect(activeWorkspaceId).toBe("trading-default");
  });

  it("should switch active workspace", () => {
    useWorkspaceStore.getState().setActiveWorkspace("risk-ops");
    expect(useWorkspaceStore.getState().activeWorkspaceId).toBe("risk-ops");
  });

  it("should save custom layout preset", () => {
    useWorkspaceStore.getState().saveCurrentAsCustom("My Custom Strategy Layout");
    const { workspaces, activeWorkspaceId } = useWorkspaceStore.getState();
    expect(workspaces.some((w) => w.name === "My Custom Strategy Layout")).toBe(true);
    expect(activeWorkspaceId).toContain("custom-");
  });

  it("should export layout JSON and re-import correctly", () => {
    const json = useWorkspaceStore.getState().exportLayoutJSON("trading-default");
    expect(json).toContain("Trading Operations");

    const success = useWorkspaceStore.getState().importLayoutJSON(json);
    expect(success).toBe(true);
  });
});
