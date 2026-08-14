import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL("./", import.meta.url)) } },
  // Next compiles TSX with the automatic JSX runtime; the test transform must match it, otherwise
  // every component test fails with "React is not defined" under the classic runtime.
  esbuild: { jsx: "automatic" },
  test: { environment: "jsdom", globals: true, setupFiles: ["./vitest.setup.ts"] },
});
