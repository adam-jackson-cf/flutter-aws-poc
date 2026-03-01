const tsEslintPlugin = require("@typescript-eslint/eslint-plugin");
const tsEslintParser = require("@typescript-eslint/parser");
const complexityMax = Number(process.env.COMPLEXITY_MAX || "10");
const functionLengthMax = Number(process.env.LENGTH_MAX || "80");
const paramMax = Number(process.env.PARAM_MAX || "5");

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
      "max-lines-per-function": [
        "error",
        {
          max: functionLengthMax,
          skipBlankLines: true,
          skipComments: true,
        },
      ],
      "max-params": ["error", paramMax],
    },
  },
];
