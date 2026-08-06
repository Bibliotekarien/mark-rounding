<script setup>
import { ref } from "vue";
import { applyTheme, currentTheme, themes } from "../theme.js";

const active = ref(currentTheme());

function pick(id) {
  applyTheme(id);
  active.value = id;
}
</script>

<template>
  <span class="theme-toggle" role="group" aria-label="Tema">
    <button
      v-for="theme in themes"
      :key="theme.id"
      :class="{ selected: active === theme.id }"
      :title="theme.label"
      :aria-label="theme.label"
      @click="pick(theme.id)"
    >
      {{ theme.icon }}
    </button>
  </span>
</template>

<style scoped>
.theme-toggle {
  display: inline-flex;
  gap: 0.25rem;
}
.theme-toggle button {
  padding: 0.3rem 0.5rem;
  line-height: 1;
}
.theme-toggle button.selected {
  border-color: var(--accent);
  background: var(--surface-2);
}
</style>
