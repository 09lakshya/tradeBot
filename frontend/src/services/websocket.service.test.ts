import { describe, it, expect } from "vitest";
import { wsService } from "@/services/websocket.service";

describe("WebSocketService", () => {
  it("should initialize in CLOSED status with OFFLINE quality", () => {
    expect(wsService.getStatus()).toBe("CLOSED");
    expect(wsService.getQuality()).toBe("OFFLINE");
  });

  it("should subscribe to topic handlers cleanly", () => {
    const handler = () => {};
    const unsubscribe = wsService.subscribe("trade_updates", handler);
    expect(typeof unsubscribe).toBe("function");
    unsubscribe();
  });
});
