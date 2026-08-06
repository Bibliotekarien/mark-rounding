<script setup>
import { computed, onMounted, ref } from "vue";
import { api } from "../api.js";
import { fmtDateRange } from "../format.js";
import RegattaMap from "../components/RegattaMap.vue";

const regattas = ref([]);
const error = ref("");

const today = new Date().toISOString().slice(0, 10);

const upcoming = computed(() =>
  regattas.value
    .filter((r) => !r.end_date || r.end_date >= today)
    .sort((a, b) => (a.start_date || "9999") < (b.start_date || "9999") ? -1 : 1)
);
const past = computed(() =>
  regattas.value.filter((r) => r.end_date && r.end_date < today)
);

onMounted(async () => {
  try {
    regattas.value = await api.regattas();
  } catch (e) {
    error.value = e.message;
  }
});

function statusText(regatta) {
  if (regatta.ongoing_races > 0) return "Race pågår nu";
  if (regatta.race_count > 0 && regatta.finished_races === regatta.race_count)
    return "Avslutad";
  if (regatta.finished_races > 0)
    return `${regatta.finished_races}/${regatta.race_count} race seglade`;
  return "";
}
</script>

<template>
  <main class="page">
    <h1>Kappseglingar</h1>
    <p class="error" v-if="error">{{ error }}</p>

    <RegattaMap :regattas="regattas" />

    <section style="margin-top: 1rem">
      <h2>Kommande och pågående</h2>
      <p v-if="!upcoming.length" class="muted">Inga kommande kappseglingar.</p>
      <div v-for="regatta in upcoming" :key="regatta.id" class="card">
        <div class="regatta-list-item">
          <div>
            <router-link :to="`/regatta/${regatta.slug}`"><strong>{{ regatta.name }}</strong></router-link>
            <div class="muted">
              {{ regatta.venue }}<span v-if="regatta.venue && regatta.start_date"> · </span>
              {{ fmtDateRange(regatta.start_date, regatta.end_date) }}
              · {{ regatta.boat_count }} båtar · {{ regatta.race_count }} race
            </div>
          </div>
          <span class="pill ongoing" v-if="regatta.ongoing_races > 0">Pågår</span>
          <span class="muted" v-else>{{ statusText(regatta) }}</span>
        </div>
      </div>
    </section>

    <section v-if="past.length">
      <h2>Tidigare</h2>
      <div v-for="regatta in past" :key="regatta.id" class="card">
        <div class="regatta-list-item">
          <div>
            <router-link :to="`/regatta/${regatta.slug}`"><strong>{{ regatta.name }}</strong></router-link>
            <div class="muted">
              {{ regatta.venue }} · {{ fmtDateRange(regatta.start_date, regatta.end_date) }}
            </div>
          </div>
          <span class="pill finished">Avslutad</span>
        </div>
      </div>
    </section>
  </main>
</template>
