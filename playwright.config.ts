import { defineConfig } from "@playwright/test";
import { join } from "node:path";

const PORT = 8123;
const PY = `"${join(process.cwd(), ".venv", "Scripts", "python.exe")}"`;
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 120_000,
  workers: 1,
  reporter: [["list"], ["json", { outputFile: ".runtime/e2e-results.json" }]],
  use: { baseURL: `http://127.0.0.1:${PORT}`, trace: "off", screenshot: "off", video: "off" },
  webServer: {
    command: `${PY} -m scripts.reset_demo && ${PY} -m scripts.run_local --mode deterministic --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
