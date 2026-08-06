<script setup>
// Ticking countdown to a planned start. Shows the RRS 26 signal moments
// (prep at -4 min, one-minute, start) so the start vessel can follow the
// sequence at a glance.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

const props = defineProps({
  plannedStart: { type: String, required: true },
  compact: { type: Boolean, default: false },
});

const now = ref(Date.now());
let timer = null;
onMounted(() => {
  timer = setInterval(() => (now.value = Date.now()), 250);
});
onBeforeUnmount(() => clearInterval(timer));

const secondsLeft = computed(() =>
  Math.ceil((Date.parse(props.plannedStart) - now.value) / 1000)
);

const display = computed(() => {
  const s = Math.max(0, secondsLeft.value);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
});

const phase = computed(() => {
  const s = secondsLeft.value;
  if (s <= 0) return "Startsignal!";
  if (s <= 60) return "Sista minuten";
  if (s <= 240) return "Förberedelsesignal given";
  return "Varningssignal given";
});

const signals = computed(() => {
  const start = Date.parse(props.plannedStart);
  const fmt = (t) =>
    new Date(t).toLocaleTimeString("sv-SE", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  return [
    { label: "Förberedelse (−4 min)", at: start - 240_000, time: fmt(start - 240_000) },
    { label: "En minut (−1 min)", at: start - 60_000, time: fmt(start - 60_000) },
    { label: "Start", at: start, time: fmt(start) },
  ];
});
</script>

<template>
  <div class="countdown" :class="{ compact, imminent: secondsLeft <= 60 && secondsLeft > 0 }">
    <span class="time">{{ display }}</span>
    <span class="phase">{{ phase }}</span>
    <ul v-if="!compact" class="signals">
      <li v-for="sig in signals" :key="sig.label" :class="{ passed: now >= sig.at }">
        {{ sig.label }} — {{ sig.time }}
      </li>
    </ul>
  </div>
</template>

<style scoped>
.countdown {
  text-align: center;
  padding: 0.5rem;
}
.time {
  display: block;
  font-size: 3.2rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
.imminent .time {
  color: var(--warn);
}
.phase {
  color: var(--text-secondary);
}
.signals {
  list-style: none;
  padding: 0;
  margin: 0.6rem 0 0;
  font-size: 0.85rem;
  color: var(--text-secondary);
}
.signals .passed {
  text-decoration: line-through;
  opacity: 0.6;
}
.compact .time {
  font-size: 1.6rem;
  display: inline;
  margin-right: 0.5rem;
}
</style>
