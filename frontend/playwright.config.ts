import { defineConfig, devices } from "@playwright/test";

/**
 * Scenario 1 in the browser (stage 7): both apps against the real hub and node, with the
 * fake LLM and parser-only normalization, on ports and databases of their own.
 */
const services = {
  SANOVIO_NODE_URL: "http://127.0.0.1:18001",
  SANOVIO_HUB_URL: "http://127.0.0.1:18000",
};

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { ...devices["Desktop Chrome"], trace: "retain-on-failure" },
  webServer: [
    {
      command: "bash e2e/serve.sh hub",
      url: "http://127.0.0.1:18000/api/v1/health",
      timeout: 120_000,
    },
    {
      command: "bash e2e/serve.sh node",
      url: "http://127.0.0.1:18001/api/v1/health",
      timeout: 120_000,
    },
    {
      command: "npm run dev --workspace apps/purchaser",
      url: "http://127.0.0.1:15173",
      env: { ...services, SANOVIO_UI_PORT: "15173" },
    },
    {
      command: "npm run dev --workspace apps/supplier",
      url: "http://127.0.0.1:15174",
      env: { ...services, SANOVIO_UI_PORT: "15174" },
    },
  ],
});
