import react from "@vitejs/plugin-react";
import { defineProject } from "vitest/config";

export default defineProject({
  plugins: [react()],
  test: { name: "ui", environment: "jsdom", globals: true, setupFiles: ["./src/test-setup.ts"] },
});
