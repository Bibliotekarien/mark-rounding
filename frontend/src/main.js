import { createApp } from "vue";
import "maplibre-gl/dist/maplibre-gl.css";
import App from "./App.vue";
import { router } from "./router.js";
import { initTheme } from "./theme.js";
import "./style.css";

initTheme();
createApp(App).use(router).mount("#app");
