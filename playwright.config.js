const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: "http://127.0.0.1:4173",
    headless: true,
    trace: "on-first-retry",
  },
  webServer: {
    command: "python3 -m http.server 4173",
    port: 4173,
    reuseExistingServer: true,
    cwd: ".",
  },
});
