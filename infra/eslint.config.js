const tsEslintPlugin = require("@typescript-eslint/eslint-plugin");
const tsEslintParser = require("@typescript-eslint/parser");
const complexityMax = Number(process.env.COMPLEXITY_MAX || "10");

module.exports = [
  {
    ignores: ["cdk.out/**", "node_modules/**"],
  },
  {
    files: ["**/*.ts"],
    languageOptions: {
      parser: tsEslintParser,
      parserOptions: {
        sourceType: "module",
      },
    },
    plugins: {
      "@typescript-eslint": tsEslintPlugin,
    },
    rules: {
      complexity: ["error", complexityMax],
    },
  },
];
