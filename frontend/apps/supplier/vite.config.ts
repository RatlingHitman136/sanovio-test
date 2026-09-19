import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The browser e2e run starts its own services on other ports (frontend/e2e).
const hub = process.env.SANOVIO_HUB_URL ?? "http://127.0.0.1:8000";
const port = Number(process.env.SANOVIO_UI_PORT ?? 5174);

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port,
    strictPort: true,
    proxy: {
      // Same origin as in production, where the hub serves this app next to its API.
      "/api": hub,
    },
  },
  test: {
    name: "supplier",
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
