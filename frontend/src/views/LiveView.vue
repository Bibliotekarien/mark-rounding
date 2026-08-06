<script setup>
// /live — the shareable "right now" entry point. Redirects to the regatta
// with an ongoing race; otherwise the nearest upcoming one; otherwise the
// most recent. The visitor lands directly in the action without scrolling.
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api.js";

const router = useRouter();
const error = ref("");

onMounted(async () => {
  try {
    const regattas = await api.regattas();
    if (!regattas.length) {
      router.replace("/");
      return;
    }
    const live = regattas.find((r) => r.live_race != null);
    if (live) {
      router.replace(`/regatta/${live.slug}?race=${live.live_race}`);
      return;
    }
    const today = new Date().toISOString().slice(0, 10);
    const upcoming = regattas
      .filter((r) => !r.end_date || r.end_date >= today)
      .sort((a, b) => ((a.start_date || "9999") < (b.start_date || "9999") ? -1 : 1));
    router.replace(`/regatta/${(upcoming[0] || regattas[0]).slug}`);
  } catch (e) {
    error.value = e.message;
  }
});
</script>

<template>
  <main class="page">
    <p class="error" v-if="error">{{ error }}</p>
    <p v-else class="muted">Letar upp pågående race …</p>
  </main>
</template>
