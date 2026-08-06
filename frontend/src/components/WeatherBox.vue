<script setup>
// Weather box for an ongoing/finished race: current conditions plus a
// short forecast. If the race has a start time, the forecast hours shown
// start there; otherwise from now.
import { computed } from "vue";
import { compass, weatherLabel, windArrow } from "../format.js";

const props = defineProps({
  weather: { type: Object, default: null },
  startedAt: { type: String, default: null },
});

const current = computed(() => props.weather?.current || null);

const forecast = computed(() => {
  const hourly = props.weather?.hourly;
  if (!hourly?.time) return [];
  const from = new Date(Math.max(Date.now(), props.startedAt ? Date.parse(props.startedAt) : 0));
  const rows = [];
  for (let i = 0; i < hourly.time.length && rows.length < 4; i++) {
    // Open-Meteo hourly times lack a Z suffix with timezone=UTC.
    const t = new Date(hourly.time[i] + (hourly.time[i].endsWith("Z") ? "" : "Z"));
    if (t < from) continue;
    rows.push({
      time: t.toLocaleTimeString("sv-SE", { hour: "2-digit", minute: "2-digit" }),
      wind: hourly.wind_speed_10m?.[i],
      gust: hourly.wind_gusts_10m?.[i],
      dir: hourly.wind_direction_10m?.[i],
      temp: hourly.temperature_2m?.[i],
      code: hourly.weather_code?.[i],
    });
  }
  return rows;
});
</script>

<template>
  <div v-if="current" class="card">
    <h3>Väder</h3>
    <div class="weather">
      <span class="big">
        {{ windArrow(current.wind_direction_10m) }}
        {{ Math.round(current.wind_speed_10m ?? 0) }}
        <small>({{ Math.round(current.wind_gusts_10m ?? 0) }})</small> m/s
      </span>
      <span>{{ compass(current.wind_direction_10m) }}</span>
      <span>{{ Math.round(current.temperature_2m ?? 0) }} °C</span>
      <span>{{ weatherLabel(current.weather_code) }}</span>
    </div>
    <table v-if="forecast.length">
      <thead>
        <tr><th>Kl (prognos)</th><th>Vind</th><th>Byar</th><th>Riktn.</th><th>Temp</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="row in forecast" :key="row.time">
          <td>{{ row.time }}</td>
          <td>{{ Math.round(row.wind ?? 0) }} m/s</td>
          <td>{{ Math.round(row.gust ?? 0) }} m/s</td>
          <td>{{ compass(row.dir) }} {{ windArrow(row.dir) }}</td>
          <td>{{ Math.round(row.temp ?? 0) }} °C</td>
          <td>{{ weatherLabel(row.code) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
