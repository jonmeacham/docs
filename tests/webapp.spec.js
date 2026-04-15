const { test, expect } = require("@playwright/test");

test.describe("schedule planner webapp", () => {
  test("loads and renders initial results", async ({ page }) => {
    await page.goto("/webapp/");

    await expect(page.getByRole("heading", { level: 1, name: "Student Schedule Planner" })).toBeVisible();
    await expect(page.locator("#summary")).not.toContainText("Loading data");
    await expect(
      page.locator('#results table.results-table tbody tr:has(td[data-col="course"])').first()
    ).toBeVisible();
  });

  test("filters by course name", async ({ page }) => {
    await page.goto("/webapp/");

    const courseInput = page.locator("#course");
    await courseInput.fill("Spanish 2");

    const rows = page.locator('#results table.results-table tbody tr:has(td[data-col="course"])');
    await expect(rows.first()).toBeVisible();
    const count = await rows.count();
    expect(count).toBeGreaterThan(0);

    for (let i = 0; i < count; i += 1) {
      await expect(rows.nth(i).locator('td[data-col="course"]')).toContainText(/Spanish 2/i);
    }
  });

  test("filters by slot + semester + graduation requirement", async ({ page }) => {
    await page.goto("/webapp/");

    await page.locator("#period").selectOption("B8");
    await page.locator("#term").selectOption("semester_1");
    await page.locator('#requirements option[value="Art"]').evaluate((el) => {
      el.selected = true;
    });
    await page.locator("#requirements").dispatchEvent("change");

    const rows = page.locator('#results table.results-table tbody tr:has(td[data-col="course"])');
    await expect(rows.first()).toBeVisible();
    const count = await rows.count();
    expect(count).toBeGreaterThan(0);

    for (let i = 0; i < count; i += 1) {
      const row = rows.nth(i);
      await expect(row.locator('td[data-col="period"]')).toHaveText("B8");
      await expect(row.locator('td[data-col="requirement"]')).toContainText(/Art/i);
    }
  });

  test("supports keyboard flow and detail aria state transitions", async ({ page }) => {
    await page.goto("/webapp/");

    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");
    await expect(page.locator("#course")).toBeFocused();

    await page.keyboard.type("Spanish 2");
    const rows = page.locator('#results table.results-table tbody tr:has(td[data-col="course"])');
    await expect(rows.first()).toBeVisible();

    const firstToggle = rows.first().locator("button.row-toggle");
    const controlsId = await firstToggle.getAttribute("aria-controls");
    expect(controlsId).toBeTruthy();
    const detailPanel = page.locator(`#${controlsId}`);

    await expect(firstToggle).toHaveAttribute("aria-expanded", "false");
    await firstToggle.evaluate((el) => el.click());
    await expect(firstToggle).toHaveAttribute("aria-expanded", "true");
    await expect(detailPanel).toBeVisible();
    await firstToggle.evaluate((el) => el.click());
    await expect(firstToggle).toHaveAttribute("aria-expanded", "false");
  });

  test("announces status changes for no-results and clear actions", async ({ page }) => {
    await page.goto("/webapp/");

    const status = page.locator("#results-status");
    const summary = page.locator("#summary");

    await page.locator("#course").fill("zzzzzzzzzz-no-match");
    await expect(summary).toContainText("0 matching course options");
    await expect(status).toContainText("No compatible course options found.");

    await page.locator("#clear-btn").click();
    await expect(status).toContainText("All filters cleared. Showing all compatible course options.");
    await expect(summary).not.toContainText("0 matching course options");
  });

  test("mobile viewport keeps content readable without horizontal overflow", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/webapp/");

    const rows = page.locator('#results table.results-table tbody tr:has(td[data-col="course"])');
    await expect(rows.first()).toBeVisible();
    await rows.first().locator("button.row-toggle").click();
    await expect(page.locator(".detail-content").first()).toBeVisible();

    const hasPageOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
    );
    expect(hasPageOverflow).toBeFalsy();
  });
});
