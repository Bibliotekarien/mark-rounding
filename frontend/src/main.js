import { createApp } from "vue";
import "maplibre-gl/dist/maplibre-gl.css";
import App from "./App.vue";
import { router } from "./router.js";
import "./style.css";

createApp(App).use(router).mount("#app");
