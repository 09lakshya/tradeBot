import { describe, it, expect, beforeEach } from "vitest";
import { useNotificationStore } from "@/stores/useNotificationStore";

describe("useNotificationStore", () => {
  beforeEach(() => {
    useNotificationStore.getState().clearAll();
  });

  it("should add a new notification correctly", () => {
    useNotificationStore.getState().addNotification({
      category: "Risk",
      severity: "warning",
      title: "Test VaR Alert",
      message: "VaR threshold exceeded.",
    });

    const notifs = useNotificationStore.getState().notifications;
    expect(notifs.length).toBe(1);
    expect(notifs[0].title).toBe("Test VaR Alert");
    expect(notifs[0].read).toBe(false);
  });

  it("should mark notification as read and archive it", () => {
    useNotificationStore.getState().addNotification({
      category: "Orders",
      severity: "success",
      title: "Order Filled",
      message: "BUY RELIANCE filled.",
    });

    const notifId = useNotificationStore.getState().notifications[0].id;
    useNotificationStore.getState().markAsRead(notifId);
    expect(useNotificationStore.getState().notifications[0].read).toBe(true);

    useNotificationStore.getState().archiveNotification(notifId);
    expect(useNotificationStore.getState().notifications[0].archived).toBe(true);
  });
});
