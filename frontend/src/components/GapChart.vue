<script setup>
// Race development chart: time behind the leader at each mark, one line
// per boat. Y axis is reversed so the leader (gap 0) reads on top and a
// growing gap sinks — matching the intuition "higher = ahead".
//
// Colors: validated 8-slot categorical palette (dataviz skill, checked
// against this app's dark surface #16233a). Color follows the boat, not
// its rank: slots are assigned once per mounted chart and kept as
// standings shift between polls. More than 8 boats → the 8 currently
// ranked highest are shown and the rest folded (noted below the chart);
// identity is never color-alone — the legend lists every series.
import {
  CategoryScale,
  Chart,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
} from "chart.js";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { fmtGap, fmtTime } from "../format.js";

Chart.register(
  LineController, LineElement, PointElement,
  CategoryScale, LinearScale, Legend, Tooltip
);

const props = defineProps({
  marks: { type: Array, required: true }, // race_progress marks incl. roundings
  leaderboard: { type: Array, required: true },
});

const MAX_SERIES = 8;
// Dark-mode categorical slots, adjacent-pair validated vs surface #16233a.
const PALETTE = [
  "#3987e5", "#d95926", "#199e70", "#c98500",
  "#d55181", "#008300", "#9085e9", "#e66767",
];
const GRID = "rgba(157, 176, 204, 0.15)";
const INK = "#9db0cc";

const canvas = ref(null);
const showTable = ref(false);
let chart = null;
const slotByBoatId = new Map(); // stable color assignment across refreshes

const gapByBoatAndMark = computed(() => {
  const map = new Map();
  for (const mark of props.marks) {
    for (const r of mark.roundings) {
      if (!map.has(r.boat.id)) map.set(r.boat.id, new Map());
      map.get(r.boat.id).set(mark.id, r);
    }
  }
  return map;
});

const shownBoats = computed(() => {
  const withData = props.leaderboard.filter(
    (e) => gapByBoatAndMark.value.has(e.boat.id)
  );
  return withData.slice(0, MAX_SERIES).map((e) => e.boat);
});

const foldedCount = computed(() => {
  const withData = props.leaderboard.filter(
    (e) => gapByBoatAndMark.value.has(e.boat.id)
  );
  return Math.max(0, withData.length - MAX_SERIES);
});

function slotFor(boatId) {
  if (!slotByBoatId.has(boatId)) {
    const used = new Set(slotByBoatId.values());
    const free = PALETTE.findIndex((_, i) => !used.has(i));
    slotByBoatId.set(boatId, free === -1 ? slotByBoatId.size % PALETTE.length : free);
  }
  return slotByBoatId.get(boatId);
}

function buildDatasets() {
  return shownBoats.value.map((boat) => {
    const color = PALETTE[slotFor(boat.id)];
    const perMark = gapByBoatAndMark.value.get(boat.id);
    return {
      label: boat.sail_number,
      data: props.marks.map((m) => perMark?.get(m.id)?.gap_seconds ?? null),
      borderColor: color,
      backgroundColor: color,
      borderWidth: 2,
      pointRadius: 4,
      pointHoverRadius: 5,
      pointHitRadius: 8,
      // 2px surface ring so overlapping markers stay separable
      pointBorderColor: "#16233a",
      pointBorderWidth: 2,
      spanGaps: true,
    };
  });
}

function render() {
  if (!canvas.value) return;
  const config = {
    type: "line",
    data: { labels: props.marks.map((m) => m.name), datasets: buildDatasets() },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        y: {
          reverse: true,
          title: { display: true, text: "Tid efter ledaren", color: INK },
          ticks: { color: INK, callback: (v) => fmtGap(Math.round(v)) },
          grid: { color: GRID },
          border: { color: GRID },
        },
        x: {
          ticks: { color: INK },
          grid: { display: false },
          border: { color: GRID },
        },
      },
      plugins: {
        legend: {
          labels: { color: INK, usePointStyle: true, pointStyle: "line" },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.dataset.label}: ${fmtGap(ctx.parsed.y)}`,
          },
        },
      },
    },
  };
  if (chart) {
    chart.data = config.data;
    chart.update();
  } else {
    chart = new Chart(canvas.value, config);
  }
}

onMounted(render);
watch(() => [props.marks, props.leaderboard], render, { deep: true });
onBeforeUnmount(() => {
  if (chart) chart.destroy();
});
</script>

<template>
  <div>
    <div class="regatta-list-item">
      <h3>Utveckling — tid efter ledaren per märke</h3>
      <button @click="showTable = !showTable">
        {{ showTable ? "Visa graf" : "Visa tabell" }}
      </button>
    </div>
    <div v-show="!showTable" style="height: 300px; position: relative">
      <canvas ref="canvas"></canvas>
    </div>
    <table v-if="showTable">
      <thead>
        <tr>
          <th>Segelnr</th>
          <th v-for="mark in marks" :key="mark.id">{{ mark.name }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="boat in shownBoats" :key="boat.id">
          <td><strong>{{ boat.sail_number }}</strong></td>
          <td v-for="mark in marks" :key="mark.id">
            <template v-if="gapByBoatAndMark.get(boat.id)?.get(mark.id)">
              {{ fmtGap(gapByBoatAndMark.get(boat.id).get(mark.id).gap_seconds) }}
              <span class="muted">{{ fmtTime(gapByBoatAndMark.get(boat.id).get(mark.id).ts) }}</span>
            </template>
            <span v-else class="muted">–</span>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="foldedCount > 0" class="muted">
      Visar de {{ shownBoats.length }} främsta båtarna — {{ foldedCount }} till syns i
      märkeslistorna nedan.
    </p>
  </div>
</template>
