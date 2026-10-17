import { expect, test, type Page } from "@playwright/test";

async function ready(page: Page) {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto("/");
  await expect(page.getByText("Policy digest")).toBeVisible();
  return errors;
}

async function runScenario(page: Page, name: RegExp, status: string) {
  const result = page.locator('[data-testid="result"]');
  const before = (await result.count()) ? await result.getAttribute("data-task-id") : null;
  await page.getByRole("button", { name }).first().click();
  await expect
    .poll(async () => ((await result.count()) ? result.getAttribute("data-task-id") : null), { timeout: 30_000 })
    .not.toBe(before);
  await expect(page.locator('[data-testid="result"]')).toHaveAttribute("data-terminal", "true", { timeout: 90_000 });
  await expect(page.locator('[data-testid="result"]')).toHaveAttribute("data-status", status);
}

const tile = (page: Page, label: string) => page.locator(".card", { has: page.getByText(label, { exact: true }) }).first();

test("P0 scenario A: safe replan completes with zero personal values to the model", async ({ page }) => {
  const errors = await ready(page);
  await runScenario(page, /Safe replan/, "COMPLETED");
  await expect(tile(page, "Customer records requested by rejected plan")).toContainText("5,000");
  await expect(tile(page, "Customer records exposed to model")).toContainText("0");
  await expect(tile(page, "Personal values exposed to model")).toContainText("0");
  await expect(tile(page, "Task outcome")).toContainText("Answered");
  await expect(page.getByText("DENIED · NOT EXECUTED")).toHaveCount(2);
  await expect(page.getByText("SELECTED", { exact: true })).toBeVisible();
  await expect(page.getByText("3. MCP execution verified")).toBeVisible();
  await expect(page.locator("table")).toContainText("West");
  expect(errors).toEqual([]);
});

test("P0 scenario B1: secret request is hard-denied", async ({ page }) => {
  const errors = await ready(page);
  await runScenario(page, /Secret request/, "BLOCKED");
  await expect(page.getByText("HARD_DENY_SECRET_DISCLOSURE").first()).toBeVisible();
  await expect(page.getByText(/No planner was invoked/)).toBeVisible();
  await expect(page.locator("body")).not.toContainText("SCOPEGUARD_TEST_SECRET");
  expect(errors).toEqual([]);
});

test("P0 scenario B2: backend credential used without exposure", async ({ page }) => {
  const errors = await ready(page);
  await runScenario(page, /Backend credential use/, "COMPLETED");
  await expect(page.getByText('{"connector":"crm","connected":true,"verification":"synthetic_local_digest"}')).toBeVisible();
  await expect(page.locator("body")).not.toContainText("SCOPEGUARD_TEST_SECRET");
  expect(errors).toEqual([]);
});

test("P1: scoped approval and compromised-agent probe", async ({ page }) => {
  const errors = await ready(page);
  await page.getByRole("button", { name: /Scoped approval/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("crm.get_customer_contact");
  await expect(dialog).toContainText("customer #105");
  await dialog.getByRole("button", { name: /Approve once/ }).click();
  await expect(page.locator('[data-testid="result"]')).toHaveAttribute("data-status", "COMPLETED", { timeout: 60_000 });
  await expect(page.locator("body")).not.toContainText("customer00105@example.com");
  await page.getByRole("button", { name: "Broad CRM export", exact: true }).click();
  await expect(page.locator('[data-testid="result"]')).toHaveAttribute("data-status", "BLOCKED", { timeout: 60_000 });
  await expect(tile(page, "Prohibited upstream dispatches")).toContainText("0");
  expect(errors).toEqual([]);
});

for (const [w, h] of [[1366, 768], [1920, 1080], [390, 844]]) {
  test(`layout has no horizontal overflow at ${w}x${h}`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h });
    await ready(page);
    await runScenario(page, /Safe replan/, "COMPLETED");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
}
