<script setup>
// Committee reporting view, reached via the secret URL. Optimized for a
// phone in one hand on a boat: pick a mark, tap sail numbers as boats
// round it. Undo, free navigation between marks and races, boat and
// course management included.
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { api } from "../api.js";
import {
  boatCodeLabel,
  fmtTime,
  logEventLabel,
  prepFlagLabel,
  raceStatusLabel,
} from "../format.js";
import StartCountdown from "../components/StartCountdown.vue";
import ThemeToggle from "../components/ThemeToggle.vue";

const route = useRoute();
const token = route.params.token;

const overview = ref(null);
const raceDetail = ref(null);
const selectedRace = ref(null);
const selectedMarkId = ref(null);
const error = ref("");
const busy = ref(false);
const panel = ref(null); // null | 'boats' | 'course' | 'penalties' | 'log'
let pollTimer = null;

const seqMinutes = ref(5);
const seqFlag = ref("P");
const penaltyCode = ref("OCS");
const log = ref([]);
const newNote = ref("");

const marks = computed(() => raceDetail.value?.marks || []);
const currentMark = computed(
  () => marks.value.find((m) => m.id === selectedMarkId.value) || null
);
const markIndex = computed(() =>
  marks.value.findIndex((m) => m.id === selectedMarkId.value)
);

const roundedBoatIds = computed(
  () => new Set((currentMark.value?.roundings || []).map((r) => r.boat.id))
);

const pendingBoats = computed(() => {
  if (!overview.value || !currentMark.value) return [];
  return overview.value.boats.filter(
    (b) => b.active && !roundedBoatIds.value.has(b.id)
  );
});

const currentRace = computed(
  () => overview.value?.races.find((r) => r.number === selectedRace.value) || null
);

const codedBoats = computed(() =>
  (raceDetail.value?.leaderboard || []).filter((entry) => entry.code)
);
const codeByBoatId = computed(() => {
  const map = {};
  for (const entry of codedBoats.value) map[entry.boat.id] = entry.code;
  return map;
});

async function loadOverview() {
  overview.value = await api.report(token);
  if (selectedRace.value == null) {
    const races = overview.value.races;
    const ongoing = races.find((r) => r.status === "ongoing");
    const next = races.find((r) => r.status !== "finished");
    selectedRace.value = (ongoing || next || races[races.length - 1])?.number ?? null;
  }
}

async function loadRace() {
  if (selectedRace.value == null) return;
  raceDetail.value = await api.reportRace(token, selectedRace.value);
  if (
    selectedMarkId.value == null ||
    !marks.value.some((m) => m.id === selectedMarkId.value)
  ) {
    selectedMarkId.value = marks.value[0]?.id ?? null;
  }
}

async function loadLog() {
  if (panel.value === "log" && selectedRace.value != null) {
    log.value = await api.raceLog(token, selectedRace.value);
  }
}

async function refresh() {
  try {
    await loadOverview();
    await loadRace();
    await loadLog();
    error.value = "";
  } catch (e) {
    error.value = e.message;
  }
}

onMounted(async () => {
  await refresh();
  pollTimer = setInterval(refresh, 20000);
});
onBeforeUnmount(() => clearInterval(pollTimer));
watch(selectedRace, loadRace);

function stepMark(delta) {
  const idx = markIndex.value + delta;
  if (idx >= 0 && idx < marks.value.length) {
    selectedMarkId.value = marks.value[idx].id;
  }
}

async function tapBoat(boat) {
  if (busy.value || !currentMark.value) return;
  busy.value = true;
  try {
    await api.addRounding(token, selectedRace.value, currentMark.value.id, boat.id);
    await refresh();
  } catch (e) {
    error.value = e.message;
    await refresh();
  } finally {
    busy.value = false;
  }
}

async function undo(rounding) {
  if (!confirm(`Ångra rundning för ${rounding.boat.sail_number}?`)) return;
  try {
    await api.undoRounding(token, rounding.id);
    await refresh();
  } catch (e) {
    error.value = e.message;
  }
}

async function setStatus(status) {
  try {
    await api.setRaceStatus(token, selectedRace.value, status);
    await refresh();
  } catch (e) {
    error.value = e.message;
  }
}

// --- start procedure ---

async function armSequence() {
  try {
    await api.startSequence(token, selectedRace.value, seqMinutes.value, seqFlag.value);
    await refresh();
  } catch (e) {
    error.value = e.message;
  }
}

async function postponeStart() {
  try {
    await api.postpone(token, selectedRace.value);
    await refresh();
  } catch (e) {
    error.value = e.message;
  }
}

async function generalRecall() {
  if (!confirm("Allmän återkallelse? Racet återgår till 'Kommande' och starttiden nollas.")) return;
  try {
    await api.generalRecall(token, selectedRace.value);
    await refresh();
  } catch (e) {
    error.value = e.message;
  }
}

// --- penalties / OCS ---

async function tagBoat(boat) {
  try {
    if (codeByBoatId.value[boat.id] === penaltyCode.value) {
      await api.clearBoatCode(token, selectedRace.value, boat.id);
    } else {
      await api.setBoatCode(token, selectedRace.value, boat.id, penaltyCode.value);
    }
    await refresh();
  } catch (e) {
    error.value = e.message;
  }
}

async function clearCode(entry) {
  try {
    await api.clearBoatCode(token, selectedRace.value, entry.boat.id);
    await refresh();
  } catch (e) {
    error.value = e.message;
  }
}

// --- protocol ---

watch(panel, loadLog);

async function submitNote() {
  if (!newNote.value.trim()) return;
  try {
    await api.addLogNote(token, selectedRace.value, newNote.value.trim());
    newNote.value = "";
    await loadLog();
  } catch (e) {
    error.value = e.message;
  }
}

// --- boat management ---
const newBoat = ref({ sail_number: "", boat_name: "", boat_type: "" });

async function addBoat() {
  if (!newBoat.value.sail_number.trim()) return;
  try {
    await api.reportAddBoat(token, newBoat.value);
    newBoat.value = { sail_number: "", boat_name: "", boat_type: "" };
    await refresh();
  } catch (e) {
    error.value = e.message;
  }
}

async function toggleBoat(boat) {
  try {
    await api.reportPatchBoat(token, boat.id, { active: !boat.active });
    await refresh();
  } catch (e) {
    error.value = e.message;
  }
}

// --- course library editing ---
const courseEdits = ref({}); // course id -> { name, marksText }
const newCourse = ref({ name: "", marksText: "" });

watch(panel, (value) => {
  if (value === "course" && overview.value) {
    const edits = {};
    for (const course of overview.value.courses) {
      edits[course.id] = {
        name: course.name,
        marksText: course.marks.map((m) => m.name).join("\n"),
      };
    }
    courseEdits.value = edits;
  }
});

function parseMarks(text) {
  return text.split("\n").map((s) => s.trim()).filter(Boolean);
}

async function saveCourse(course) {
  const edit = courseEdits.value[course.id];
  const names = parseMarks(edit.marksText);
  if (!names.length || !edit.name.trim()) return;
  if (
    course.marks.length > names.length &&
    !confirm(
      "Banan får färre märken — rundningar vid borttagna märken raderas i race som seglar den. Fortsätt?"
    )
  ) {
    return;
  }
  try {
    await api.reportPatchCourse(token, course.id, {
      name: edit.name.trim(),
      marks: names,
    });
    await refresh();
  } catch (e) {
    error.value = e.message;
  }
}

async function removeCourse(course) {
  if (!confirm(`Ta bort banan ${course.name}?`)) return;
  try {
    await api.reportDeleteCourse(token, course.id);
    await refresh();
  } catch (e) {
    error.value = e.message;
  }
}

async function addCourse() {
  const names = parseMarks(newCourse.value.marksText);
  if (!newCourse.value.name.trim() || !names.length) return;
  try {
    const created = await api.reportAddCourse(token, {
      name: newCourse.value.name.trim(),
      marks: names,
    });
    newCourse.value = { name: "", marksText: "" };
    await refresh();
    courseEdits.value[created.id] = {
      name: created.name,
      marksText: created.marks.map((m) => m.name).join("\n"),
    };
  } catch (e) {
    error.value = e.message;
  }
}

// --- per-race course + shortening ---

async function changeRaceCourse(event) {
  try {
    await api.setRaceCourse(token, selectedRace.value, Number(event.target.value));
    await refresh();
  } catch (e) {
    error.value = e.message;
    await refresh();
  }
}

async function shorten() {
  if (
    !confirm(
      "Avkorta banan (S)? Racet avslutas nu — rundningarna vid senaste märket räknas som målgång."
    )
  )
    return;
  try {
    await api.shortenRace(token, selectedRace.value);
    await refresh();
  } catch (e) {
    error.value = e.message;
  }
}
</script>

<template>
  <main class="page" v-if="overview">
    <div class="regatta-list-item">
      <h1 style="font-size: 1.2rem">{{ overview.name }}</h1>
      <span style="display: inline-flex; align-items: center; gap: 0.6rem">
        <ThemeToggle />
        <span class="muted">Rapportering</span>
      </span>
    </div>
    <p class="error" v-if="error">{{ error }}</p>

    <div class="selector-row">
      <button
        v-for="race in overview.races"
        :key="race.number"
        :class="{ selected: race.number === selectedRace }"
        @click="selectedRace = race.number"
      >
        Race {{ race.number }}
      </button>
      <span class="spacer" style="flex: 1"></span>
      <button :class="{ selected: panel === 'penalties' }" @click="panel = panel === 'penalties' ? null : 'penalties'">Straff</button>
      <button :class="{ selected: panel === 'log' }" @click="panel = panel === 'log' ? null : 'log'">Protokoll</button>
      <button :class="{ selected: panel === 'boats' }" @click="panel = panel === 'boats' ? null : 'boats'">Båtar</button>
      <button :class="{ selected: panel === 'course' }" @click="panel = panel === 'course' ? null : 'course'">Bana</button>
    </div>

    <!-- start procedure -->
    <div v-if="currentRace" class="card">
      <div class="regatta-list-item">
        <span class="pill" :class="currentRace.status">
          {{ raceStatusLabel[currentRace.status] }}
          <template v-if="currentRace.started_at"> · start {{ fmtTime(currentRace.started_at) }}</template>
        </span>
        <span class="muted" v-if="currentRace.general_recalls > 0">
          {{ currentRace.general_recalls }} allmän(na) återkallelse(r)
        </span>
      </div>

      <!-- upcoming, no countdown armed: pick course, arm the sequence -->
      <template v-if="currentRace.status === 'upcoming' && !currentRace.planned_start">
        <div class="field" style="margin-top: 0.5rem">
          <label>Bana för race {{ selectedRace }}</label>
          <select :value="currentRace.course_id ?? ''" @change="changeRaceCourse">
            <option value="" disabled>Välj bana …</option>
            <option v-for="course in overview.courses" :key="course.id" :value="course.id">
              {{ course.name }} ({{ course.marks.map((m) => m.name).join(" → ") }})
            </option>
          </select>
        </div>
        <p v-if="!currentRace.course_id" class="error">
          Välj bana innan racet startas.
        </p>
        <div class="grid-2">
          <div class="field">
            <label>Nedräkning (minuter)</label>
            <input type="number" min="1" max="60" v-model.number="seqMinutes" />
          </div>
          <div class="field">
            <label>Förberedelseflagga</label>
            <select v-model="seqFlag">
              <option v-for="(label, flag) in prepFlagLabel" :key="flag" :value="flag">{{ label }}</option>
            </select>
          </div>
        </div>
        <button class="primary" @click="armSequence" :disabled="!currentRace.course_id">
          Starta sekvens ({{ seqMinutes }} min)
        </button>
        <button style="margin-left: 0.5rem" @click="setStatus('ongoing')" :disabled="!currentRace.course_id">
          Start utan sekvens
        </button>
      </template>

      <!-- countdown running -->
      <template v-else-if="currentRace.status === 'upcoming' && currentRace.planned_start">
        <StartCountdown :planned-start="currentRace.planned_start" />
        <p class="muted" style="text-align: center">
          Flagga {{ prepFlagLabel[currentRace.prep_flag] || currentRace.prep_flag }}
        </p>
        <div class="selector-row" style="justify-content: center">
          <button class="primary" @click="setStatus('ongoing')">Startsignal given</button>
          <button class="danger" @click="postponeStart">AP — uppskjut</button>
        </div>
      </template>

      <!-- ongoing / finished -->
      <template v-else>
        <p class="muted" v-if="currentRace.course_name" style="margin: 0.3rem 0 0">
          Bana: {{ currentRace.course_name }}
          <span v-if="currentRace.shortened"> · Avkortad (S)</span>
        </p>
        <div class="selector-row" style="margin: 0.5rem 0 0">
          <button v-if="currentRace.status === 'ongoing'" class="primary" @click="setStatus('finished')">
            Avsluta race
          </button>
          <button v-if="currentRace.status === 'ongoing'" @click="shorten">
            Avkorta & avsluta (S)
          </button>
          <button v-if="currentRace.status === 'ongoing'" class="danger" @click="generalRecall">
            Allmän återkallelse
          </button>
          <button v-if="currentRace.status === 'finished'" @click="setStatus('ongoing')">
            Återöppna
          </button>
        </div>
      </template>
    </div>

    <!-- penalties / OCS panel -->
    <div v-if="panel === 'penalties'" class="card">
      <h3>Tjuvstarter och straff</h3>
      <p class="muted">
        Välj kod och tryck på båtarna. Tryck igen för att ångra. OCS/BFD/UFD
        flyttas längst ner i resultatet; ZFP behåller sin placering.
      </p>
      <div class="selector-row">
        <button
          v-for="(label, code) in boatCodeLabel"
          :key="code"
          :class="{ selected: penaltyCode === code }"
          @click="penaltyCode = code"
        >
          {{ code }}
        </button>
      </div>
      <p class="muted">{{ boatCodeLabel[penaltyCode] }}</p>
      <div class="boat-grid">
        <button
          v-for="boat in overview.boats.filter((b) => b.active)"
          :key="boat.id"
          :class="{ tagged: codeByBoatId[boat.id] }"
          @click="tagBoat(boat)"
        >
          {{ boat.sail_number }}
          <span class="boat-sub">{{ codeByBoatId[boat.id] ? boatCodeLabel[codeByBoatId[boat.id]] : boat.boat_name || boat.boat_type }}</span>
        </button>
      </div>
      <template v-if="codedBoats.length">
        <h4 style="margin-top: 1rem">Markerade i race {{ selectedRace }}</h4>
        <ul class="rounding-list">
          <li v-for="entry in codedBoats" :key="entry.boat.id">
            <strong>{{ entry.boat.sail_number }}</strong>
            <span class="pill">{{ boatCodeLabel[entry.code] }}</span>
            <span class="spacer"></span>
            <button class="danger" @click="clearCode(entry)">Ta bort</button>
          </li>
        </ul>
      </template>
    </div>

    <!-- protocol panel -->
    <div v-if="panel === 'log'" class="card">
      <h3>Protokoll — race {{ selectedRace }}</h3>
      <p v-if="!log.length" class="muted">Inga händelser ännu.</p>
      <table v-else>
        <tbody>
          <tr v-for="entry in log" :key="entry.id">
            <td style="white-space: nowrap">{{ fmtTime(entry.ts) }}</td>
            <td>{{ logEventLabel[entry.event] || entry.event }}</td>
            <td><strong>{{ entry.sail_number || "" }}</strong></td>
            <td>{{ entry.note }}</td>
          </tr>
        </tbody>
      </table>
      <div class="field" style="margin-top: 0.75rem">
        <label>Ny anteckning</label>
        <textarea v-model="newNote" rows="2" placeholder="T.ex. vindvrid, protest, observation …"></textarea>
      </div>
      <button class="primary" @click="submitNote" :disabled="!newNote.trim()">
        Lägg till i protokollet
      </button>
    </div>

    <!-- boat management panel -->
    <div v-if="panel === 'boats'" class="card">
      <h3>Båtar</h3>
      <div class="grid-2">
        <div class="field">
          <label>Segelnummer</label>
          <input v-model="newBoat.sail_number" placeholder="SWE 123" />
        </div>
        <div class="field">
          <label>Båtnamn</label>
          <input v-model="newBoat.boat_name" />
        </div>
      </div>
      <button class="primary" @click="addBoat" :disabled="!newBoat.sail_number.trim()">
        Lägg till båt
      </button>
      <table style="margin-top: 0.75rem">
        <tbody>
          <tr v-for="boat in overview.boats" :key="boat.id">
            <td><strong>{{ boat.sail_number }}</strong></td>
            <td>{{ boat.boat_name }}</td>
            <td class="muted">{{ boat.active ? "Deltar" : "Utgått" }}</td>
            <td style="text-align: right">
              <button @click="toggleBoat(boat)">
                {{ boat.active ? "Ta bort ur race" : "Ta med igen" }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- course library panel -->
    <div v-if="panel === 'course'" class="card">
      <h3>Banor</h3>
      <p class="muted">
        Definiera banorna här och välj bana per race i startpanelen.
        Ett märke per rad, i rundningsordning.
      </p>
      <div v-for="course in overview.courses" :key="course.id" class="card" style="margin-bottom: 0.75rem">
        <div class="field">
          <label>Namn</label>
          <input v-if="courseEdits[course.id]" v-model="courseEdits[course.id].name" />
        </div>
        <div class="field">
          <label>Märken</label>
          <textarea v-if="courseEdits[course.id]" v-model="courseEdits[course.id].marksText" rows="4"></textarea>
        </div>
        <button class="primary" @click="saveCourse(course)">Spara</button>
        <button class="danger" style="margin-left: 0.5rem" @click="removeCourse(course)">Ta bort</button>
      </div>
      <h4>Ny bana</h4>
      <div class="field">
        <label>Namn</label>
        <input v-model="newCourse.name" placeholder="T.ex. Kryss-läns 2 varv" />
      </div>
      <div class="field">
        <label>Märken</label>
        <textarea v-model="newCourse.marksText" rows="4" placeholder="Start&#10;Kryssmärke&#10;Länsmärke&#10;Mål"></textarea>
      </div>
      <button class="primary" @click="addCourse" :disabled="!newCourse.name.trim() || !newCourse.marksText.trim()">
        Lägg till bana
      </button>
    </div>

    <!-- mark navigation -->
    <div class="selector-row" v-if="marks.length">
      <button :disabled="markIndex <= 0" @click="stepMark(-1)">←</button>
      <button
        v-for="mark in marks"
        :key="mark.id"
        :class="{ selected: mark.id === selectedMarkId }"
        @click="selectedMarkId = mark.id"
      >
        {{ mark.name }}
        <small>({{ mark.roundings.length }})</small>
      </button>
      <button :disabled="markIndex >= marks.length - 1" @click="stepMark(1)">→</button>
    </div>
    <p v-else class="muted">
      Ingen bana vald för det här racet — definiera banor under ”Bana” och
      välj sedan bana i startpanelen ovan.
    </p>

    <template v-if="currentMark">
      <div class="card">
        <h3>Rundar {{ currentMark.name }} — tryck på segelnumret</h3>
        <p v-if="!pendingBoats.length" class="muted">
          Alla aktiva båtar har rundat det här märket.
        </p>
        <div class="boat-grid">
          <button v-for="boat in pendingBoats" :key="boat.id" @click="tapBoat(boat)" :disabled="busy">
            {{ boat.sail_number }}
            <span class="boat-sub">{{ boat.boat_name || boat.boat_type }}</span>
          </button>
        </div>
      </div>

      <div class="card">
        <h3>Rundningsordning vid {{ currentMark.name }}</h3>
        <p v-if="!currentMark.roundings.length" class="muted">Inga rundningar ännu.</p>
        <ul class="rounding-list">
          <li v-for="rounding in currentMark.roundings" :key="rounding.id">
            <span class="pos">{{ rounding.position }}</span>
            <strong>{{ rounding.boat.sail_number }}</strong>
            <span class="muted">{{ rounding.boat.boat_name }}</span>
            <span class="spacer"></span>
            <span class="muted">{{ fmtTime(rounding.ts) }}</span>
            <button class="danger" @click="undo(rounding)">Ångra</button>
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
