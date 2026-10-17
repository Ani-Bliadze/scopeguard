// Captures real dashboard screenshots after each scenario reaches its asserted end state.
// Usage: node scripts/capture_demo.mjs [--url http://127.0.0.1:8000] [--out docs/screenshots] [--size 1920x1080]
// Saves no cookies, traces or HAR files.
import { chromium } from "@playwright/test";
import { mkdirSync, copyFileSync } from "node:fs";
import { join } from "node:path";

const arg = (name, dflt) => {
  const i = process.argv.indexOf(name);
  return i > 0 ? process.argv[i + 1] : dflt;
};
const URL = arg("--url", process.env.SCOPEGUARD_URL ?? "http://127.0.0.1:8000");
const OUT = arg("--out", "docs/screenshots");
const [W, H] = arg("--size", "1600x1000").split("x").map(Number);
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
const page = await context.newPage();
const consoleErrors = [];
page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));

let lastTaskId = null;
async function waitTerminal(expect) {
  await page.waitForFunction(
    (prev) => {
      const el = document.querySelector('[data-testid="result"]');
      return el && el.getAttribute("data-task-id") !== prev && el.getAttribute("data-terminal") === "true";
    },
    lastTaskId,
    { timeout: 90_000 },
  );
  lastTaskId = await page.getAttribute('[data-testid="result"]', "data-task-id");
  const status = await page.getAttribute('[data-testid="result"]', "data-status");
  if (expect && status !== expect) throw new Error(`expected ${expect}, got ${status}`);
  await page.waitForTimeout(700); // let the final poll render events
  return status;
}

async function clickScenario(title) {
  console.log("scenario:", title);
  await page.getByRole("button", { name: new RegExp(title) }).first().click();
  await page.waitForTimeout(300);
}

const shots = [];
async function shot(name, fullPage = false) {
  const file = join(OUT, `${name}.png`);
  await page.screenshot({ path: file, fullPage });
  shots.push(file);
}

await page.goto(URL);
await page.waitForSelector("text=Policy digest");
await page.waitForLoadState("networkidle");
await page.getByRole("button", { name: /Reset demo/ }).click();
await page.waitForResponse((r) => r.url().endsWith("/api/demo/session") && r.status() === 200, { timeout: 30_000 });
await page.waitForLoadState("networkidle");
console.log("reset done");

await clickScenario("Safe replan");
await waitTerminal("COMPLETED");
await shot(`demo-sales-${W}x${H}`);
await shot(`demo-sales-full`, true);

await clickScenario("Secret request");
await waitTerminal("BLOCKED");
await shot(`demo-secret-${W}x${H}`);

await clickScenario("Backend credential use");
await waitTerminal("COMPLETED");
await shot(`demo-connection-${W}x${H}`);

await page.getByRole("button", { name: "Broad CRM export", exact: true }).click();
await waitTerminal("BLOCKED");
await shot(`demo-probe-${W}x${H}`);

await clickScenario("Scoped approval");
await page.waitForSelector('[role="dialog"]', { timeout: 60_000 });
await page.waitForTimeout(500);
await shot(`demo-approval-request-${W}x${H}`);
await page.getByRole("button", { name: /Approve once/ }).click();
await waitTerminal("COMPLETED");
await shot(`demo-approval-done-${W}x${H}`);

await page.getByRole("button", { name: /Policy/ }).click();
await page.waitForTimeout(600);
await shot(`demo-policy-${W}x${H}`);

await browser.close();
if (consoleErrors.length) {
  console.error("console errors:", consoleErrors);
  process.exit(1);
}
// Optionally copy the deck's evidence screenshots (--assets)
if (process.argv.includes("--assets")) {
  mkdirSync("pitch/assets", { recursive: true });
  for (const n of ["sales", "secret", "connection", "probe", "approval-request"]) {
    copyFileSync(join(OUT, `demo-${n}-${W}x${H}.png`), `pitch/assets/demo-${n}.png`);
  }
}
console.log("captured", shots.length, "screenshots ->", OUT);
