// ESLint flat config. The main job is catching real errors that Vite's
// build never sees — undefined identifiers above all (a stale constant
// name once crashed the gap chart at runtime with a green build).
// vue/flat/essential keeps it to correctness rules, no formatting nits.
import js from "@eslint/js";
import vue from "eslint-plugin-vue";
import globals from "globals";

export default [
  { ignores: ["dist/"] },
  js.configs.recommended,
  ...vue.configs["flat/essential"],
  {
    languageOptions: {
      globals: { ...globals.browser },
    },
  },
];
