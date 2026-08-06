<script setup>
import { useRoute } from "vue-router";
import { computed } from "vue";
import ThemeToggle from "./components/ThemeToggle.vue";

const route = useRoute();
// The committee report view keeps its own minimal header (big tap targets,
// no navigation temptations); everyone else gets the shared top bar.
const showTopbar = computed(() => !route.path.startsWith("/report/"));
</script>

<template>
  <header v-if="showTopbar" class="topbar">
    <router-link class="brand" to="/">⛵ Mark-rounding</router-link>
    <span class="spacer"></span>
    <ThemeToggle />
    <router-link to="/admin" class="muted">Admin</router-link>
  </header>
  <router-view />
</template>
