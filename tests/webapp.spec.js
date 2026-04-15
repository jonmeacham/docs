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
});
