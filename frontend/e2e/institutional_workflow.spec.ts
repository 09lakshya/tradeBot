import { test, expect } from "@playwright/test";

test.describe("Institutional Dashboard Production Readiness E2E Suite", () => {
  test("loads main dashboard and displays status bar, quality indicator, and widgets", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("text=Institutional Quantitative Dashboard")).toBeVisible();
    await expect(page.locator("text=NSE/BSE Indian Equities")).toBeVisible();
    await expect(page.locator("text=Workspace:")).toBeVisible();
  });

  test("allows switching workspace presets and opening notification center", async ({ page }) => {
    await page.goto("/");
    await page.click("text=Risk & Compliance");
    await expect(page.locator("text=Exposures & Concentration")).toBeVisible();

    await page.click("button[title='Open Notification Center']");
    await expect(page.locator("text=NOTIFICATION CENTER")).toBeVisible();
  });
});
