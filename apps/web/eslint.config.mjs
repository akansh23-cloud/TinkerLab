import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { FlatCompat } from "@eslint/eslintrc";

// Phase-6 stabilization: `npm run lint` previously failed because no ESLint 9 flat config existed.
const compat = new FlatCompat({ baseDirectory: dirname(fileURLToPath(import.meta.url)) });

const config = [
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts"] },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      // Scientific payloads are validated by the API contract; `unknown`/`Record<string, unknown>`
      // is used deliberately at those seams, but genuine `any` remains an error.
      "@typescript-eslint/no-explicit-any": "error",
    },
  },
];

export default config;
