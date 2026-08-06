import { createRouter, createWebHistory } from "vue-router";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: () => import("./views/HomeView.vue") },
    { path: "/regatta/:slug", component: () => import("./views/RegattaView.vue") },
    { path: "/report/:token", component: () => import("./views/ReportView.vue") },
    { path: "/admin", component: () => import("./views/AdminView.vue") },
  ],
});
