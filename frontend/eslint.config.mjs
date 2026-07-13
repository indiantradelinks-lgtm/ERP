// ESLint 9 flat config — catches undeclared identifiers (no-undef) which would
// have flagged the iter4 FileUploader `progress` regression before deploy.
import js from "@eslint/js";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

export default [
  js.configs.recommended,
  {
    files: ["src/**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
      globals: {
        ...globals.browser,
        ...globals.node,
        process: "readonly",
      },
    },
    plugins: {
      react,
      "react-hooks": reactHooks,
    },
    settings: { react: { version: "detect" } },
    rules: {
      // Catch undeclared identifiers — the rule that would have caught iter4 FileUploader bug
      "no-undef": "error",

      // Mirror CRA's react-app preset noise levels
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      "no-empty": ["error", { allowEmptyCatch: true }],

      // JSX awareness
      "react/jsx-uses-react": "off",
      "react/jsx-uses-vars": "error",
      "react/react-in-jsx-scope": "off",

      // Hooks discipline
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
    },
  },
  {
    // Don't lint generated / vendor bundles
    ignores: [
      "build/**",
      "node_modules/**",
      "public/**",
      "src/components/ui/**",
    ],
  },
];
