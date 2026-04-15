const { test, expect } = require("@playwright/test");

test.describe("schedule builder", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/webapp/builder.html");
    await page.evaluate(() => {
      localStorage.removeItem("lhs.builder.current");
      localStorage.removeItem("lhs.builder.saves");
      localStorage.removeItem("lhs.builder.completed");
    });
    await page.reload();
  });

  test("loads builder page and schedule rows", async ({ page }) => {
    await expect(page.getByRole("heading", { level: 1, name: "Schedule Builder" })).toBeVisible();
    await expect(page.locator("#schedule-rows tr")).toHaveCount(8);
    await expect(page.locator('a[href="./index.html"]')).toBeVisible();
  });

  test("autosaves draft and restores after reload", async ({ page }) => {
    await page.locator("#student-name").fill("Test Student");
    await page.locator('[data-period="A1"][data-field="semester1"]').fill("English 10");

    await page.waitForTimeout(700);
    await page.reload();

    await expect(page.locator("#student-name")).toHaveValue("Test Student");
    await expect(page.locator('[data-period="A1"][data-field="semester1"]')).toHaveValue("English 10");
    await expect(page.locator("#save-status")).toContainText("Saved");
  });

  test("saves and restores a named checkpoint", async ({ page }) => {
    await page.locator("#student-name").fill("Checkpoint Student");
    await page.locator('[data-period="A2"][data-field="semester1"]').fill("Biology");
    await page.locator("#checkpoint-name").fill("First pass");
    await page.locator("#save-checkpoint-btn").click();

    await page.locator('[data-period="A2"][data-field="semester1"]').fill("Changed Course");
    await page.locator("#checkpoint-select").selectOption({ index: 1 });
    await page.locator("#restore-checkpoint-btn").click();

    await expect(page.locator('[data-period="A2"][data-field="semester1"]')).toHaveValue("Biology");
    await expect(page.locator("#validation-status")).toContainText('Restored checkpoint "First pass"');
  });

  test("marks schedule complete and triggers export print", async ({ page }) => {
    await page.addInitScript(() => {
      window.__printCalled = false;
      const original = window.print;
      window.print = () => {
        window.__printCalled = true;
        return original?.();
      };
    });
    await page.reload();

    await page.evaluate(() => {
      document.getElementById("student-name").value = "Complete Student";
      document.getElementById("student-grade").value = "10th Grade (2026-27)";
      for (const period of ["A1", "A2", "A3", "A4", "B5", "B6", "B7", "B8"]) {
        document.querySelector(`[data-period="${period}"][data-field="semester1"]`).value = `Course ${period} S1`;
        document.querySelector(`[data-period="${period}"][data-field="semester2"]`).value = `Course ${period} S2`;
      }
    });

    await page.locator("#mark-complete-btn").click();
    await expect(page.locator("#completion-status")).toContainText("Complete");

    await page.locator("#export-pdf-btn").click();
    const printCalled = await page.evaluate(() => window.__printCalled);
    expect(printCalled).toBeTruthy();
  });
});
