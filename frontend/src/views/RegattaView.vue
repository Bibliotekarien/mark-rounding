<script setup>
// Public regatta page: navigate between races, follow the ongoing one.
// Polls every 15 s so spectators see roundings as they are reported.
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { api } from "../api.js";
import {
  boatCodeLabel,
  fmtDateRange,
  fmtGap,
  fmtTime,
  raceStatusLabel,
} from "../format.js";
import GapChart from "../components/GapChart.vue";
import StartCountdown from "../components/StartCountdown.vue";
import WeatherBox from "../components/WeatherBox.vue";

const route = useRoute();
const regatta = ref(null);
const raceDetail = ref(null);
const weather = ref(null);
const selectedRace = ref(null);
const error = ref("");
let pollTimer = null;

const currentRace = computed(() =>
  regatta.value?.races.find((r) => r.number === selectedRace.value) || null
);

const showWeather = computed(
  () => currentRace.value && currentRace.value.status !== "upcoming"
);

const boatsWithRoundings = computed(() => {
  if (!raceDetail.value) return 0;
  const ids = new Set();
  for (const mark of raceDetail.value.marks) {
    for (const r of mark.roundings) ids.add(r.boat.id);
  }
  return ids.size;
});

async function loadRegatta() {
  regatta.value = await api.regatta(route.params.slug);
  if (selectedRace.value == null) {
    // Default to the ongoing race, else the first not-finished, else the last.
    const races = regatta.value.races;
    const ongoing = races.find((r) => r.status === "ongoing");
    const next = races.find((r) => r.status !== "finished");
    selectedRace.value = (ongoing || next || races[races.length - 1])?.number ?? null;
  }
}

async function loadRace() {
  if (selectedRace.value == null) return;
  raceDetail.value = await api.race(route.params.slug, selectedRace.value);
}

async function loadWeather() {
  try {
    weather.value = await api.weather(route.params.slug);
  } catch {
    weather.value = null; // no coordinates or upstream down — box just hides
  }
}

async function refresh() {
  try {
    await loadRegatta();
    await loadRace();
    error.value = "";
  } catch (e) {
    error.value = e.message;
  }
}

onMounted(async () => {
  await refresh();
  await loadWeather();
  pollTimer = setInterval(refresh, 15000);
});

onBeforeUnmount(() => clearInterval(pollTimer));

watch(selectedRace, loadRace);
</script>

<template>
  <main class="page" v-if="regatta">
    <h1>{{ regatta.name }}</h1>
    <p class="muted">
      {{ regatta.venue }}<span v-if="regatta.venue"> · </span>
      {{ fmtDateRange(regatta.start_date, regatta.end_date) }}
      <span v-if="regatta.organizer"> · {{ regatta.organizer }}</span>
    </p>
    <p class="error" v-if="error">{{ error }}</p>

    <div class="selector-row">
      <button
        v-for="race in regatta.races"
        :key="race.number"
        :class="{ selected: race.number === selectedRace }"
        @click="selectedRace = race.number"
      >
        Race {{ race.number }}
        <span v-if="race.status === 'ongoing'">●</span>
      </button>
    </div>

    <div v-if="currentRace" class="card">
      <div class="regatta-list-item">
        <h2>Race {{ currentRace.number }}</h2>
        <span class="pill" :class="currentRace.status">
          {{ raceStatusLabel[currentRace.status] }}
          <template v-if="currentRace.started_at"> · start {{ fmtTime(currentRace.started_at) }}</template>
        </span>
      </div>
      <p class="muted" v-if="currentRace.general_recalls > 0" style="margin: 0.3rem 0 0">
        {{ currentRace.general_recalls }} allmän(na) återkallelse(r)
      </p>
      <StartCountdown
        v-if="currentRace.status === 'upcoming' && currentRace.planned_start"
        :planned-start="currentRace.planned_start"
      />
    </div>

    <WeatherBox
      v-if="showWeather"
      :weather="weather"
      :started-at="currentRace?.started_at"
    />

    <template v-if="raceDetail">
      <div class="card">
        <h3>Ställning</h3>
        <p v-if="!raceDetail.leaderboard.length" class="muted">Inga båtar ännu.</p>
        <table v-else>
          <thead>
            <tr><th>#</th><th>Segelnr</th><th>Båt</th><th>Senaste märke</th><th>Tid</th></tr>
          </thead>
          <tbody>
            <tr v-for="(entry, i) in raceDetail.leaderboard" :key="entry.boat.id">
              <td>{{ entry.last_mark_seq != null && (!entry.code || entry.code === 'ZFP') ? i + 1 : "–" }}</td>
              <td><strong>{{ entry.boat.sail_number }}</strong></td>
              <td>
                {{ entry.boat.boat_name }}
                <span class="muted" v-if="entry.boat.boat_type"> · {{ entry.boat.boat_type }}</span>
              </td>
              <td>
                <span v-if="entry.code" class="pill" :class="{ upcoming: entry.code === 'ZFP' }">
                  {{ boatCodeLabel[entry.code] || entry.code }}
                </span>
                <template v-if="!entry.code">{{ entry.last_mark_name || "Ej startat/rapporterad" }}</template>
                <template v-else-if="entry.last_mark_name"> {{ entry.last_mark_name }}</template>
              </td>
              <td>{{ fmtTime(entry.last_ts) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card" v-if="boatsWithRoundings >= 2">
        <GapChart :marks="raceDetail.marks" :leaderboard="raceDetail.leaderboard" />
      </div>

      <div class="card" v-for="mark in raceDetail.marks" :key="mark.id">
        <h3>{{ mark.seq }}. {{ mark.name }}</h3>
        <p v-if="!mark.roundings.length" class="muted">Inga rundningar ännu.</p>
        <ul v-else class="rounding-list">
          <li v-for="rounding in mark.roundings" :key="rounding.id">
            <span class="pos">{{ rounding.position }}</span>
            <strong>{{ rounding.boat.sail_number }}</strong>
            <span class="muted">{{ rounding.boat.boat_name }}</span>
            <span class="spacer"></span>
            <span v-if="rounding.position > 1" class="muted">{{ fmtGap(rounding.gap_seconds) }}</span>
            <span class="muted">{{ fmtTime(rounding.ts) }}</span>
          </li>
        </ul>
      </div>
    </template>
  </main>
  <main class="page" v-else>
    <p class="error" v-if="error">{{ error }}</p>
    <p v-else class="muted">Laddar …</p>
  </main>
</template>
