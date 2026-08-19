<script setup>
// Admin: log in, define regattas (venue, dates, course, race count),
// import participants from Sailarena, manage the boat list and hand out
// the secret reporting URL.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { api, hasAdminToken, setAdminToken } from "../api.js";
import { fmtDateRange, raceStatusLabel } from "../format.js";

const loggedIn = ref(hasAdminToken());
const password = ref("");
const error = ref("");
const notice = ref("");

const regattas = ref([]);
const editing = ref(null); // full admin regatta detail, or null for list view
const creating = ref(false);

const blankForm = () => ({
  name: "",
  venue: "",
  organizer: "",
  lat: null,
  lon: null,
  start_date: "",
  end_date: "",
  sailarena_url: "",
  race_count: 1,
  course_name: "Bana 1",
  marks: "Start\nKryssmärke 1\nLänsmärke\nMål",
});
const form = ref(blankForm());
const previewBoats = ref([]);
const previewLoading = ref(false);

function onUnauthorized() {
  loggedIn.value = false;
}

onMounted(() => {
  window.addEventListener("markrounding:unauthorized", onUnauthorized);
  if (loggedIn.value) loadList();
});
onBeforeUnmount(() =>
  window.removeEventListener("markrounding:unauthorized", onUnauthorized)
);

async function login() {
  error.value = "";
  try {
    const { token } = await api.login(password.value);
    setAdminToken(token);
    password.value = "";
    loggedIn.value = true;
    await loadList();
  } catch (e) {
    error.value = e.message;
  }
}

function logout() {
  setAdminToken(null);
  loggedIn.value = false;
  editing.value = null;
}

async function loadList() {
  try {
    regattas.value = await api.adminRegattas();
    error.value = "";
  } catch (e) {
    if (e.status !== 401) error.value = e.message;
  }
}

// --- create flow ---

async function fetchSailarena() {
  if (!form.value.sailarena_url) return;
  previewLoading.value = true;
  error.value = "";
  try {
    const preview = await api.sailarenaPreview(form.value.sailarena_url);
    if (preview.name && !form.value.name) form.value.name = preview.name;
    if (preview.lat != null) form.value.lat = preview.lat;
    if (preview.lon != null) form.value.lon = preview.lon;
    if (preview.start_date && !form.value.start_date) form.value.start_date = preview.start_date;
    if (preview.end_date && !form.value.end_date) form.value.end_date = preview.end_date;
    previewBoats.value = preview.boats || [];
    notice.value = `Hämtade ${previewBoats.value.length} båtar från Sailarena.`;
  } catch (e) {
    error.value = e.message;
  } finally {
    previewLoading.value = false;
  }
}

async function createRegatta() {
  error.value = "";
  try {
    const markNames = form.value.marks.split("\n").map((s) => s.trim()).filter(Boolean);
    const body = {
      ...form.value,
      lat: form.value.lat === "" ? null : form.value.lat,
      lon: form.value.lon === "" ? null : form.value.lon,
      start_date: form.value.start_date || null,
      end_date: form.value.end_date || null,
      courses: markNames.length
        ? [{ name: form.value.course_name.trim() || "Bana 1", marks: markNames }]
        : [],
    };
    delete body.course_name;
    delete body.marks;
    const regatta = await api.createRegatta(body);
    if (previewBoats.value.length) {
      await api.importBoats(regatta.id, previewBoats.value, false);
    }
    creating.value = false;
    form.value = blankForm();
    previewBoats.value = [];
    await loadList();
    await openRegatta(regatta.id);
  } catch (e) {
    error.value = e.message;
  }
}

// --- edit flow ---

const editForm = ref(null);
const editCourses = ref({}); // course id -> { name, marksText }
const newEditCourse = ref({ name: "", marksText: "" });
const importUrl = ref("");

async function openRegatta(id) {
  const detail = await api.adminRegatta(id);
  editing.value = detail;
  editForm.value = {
    name: detail.name,
    venue: detail.venue,
    organizer: detail.organizer,
    lat: detail.lat,
    lon: detail.lon,
    start_date: detail.start_date || "",
    end_date: detail.end_date || "",
    sailarena_url: detail.sailarena_url,
    race_count: detail.races.length,
  };
  const edits = {};
  for (const course of detail.courses) {
    edits[course.id] = {
      name: course.name,
      marksText: course.marks.map((m) => m.name).join("\n"),
    };
  }
  editCourses.value = edits;
  importUrl.value = detail.sailarena_url;
  notice.value = "";
}

function parseMarks(text) {
  return text.split("\n").map((s) => s.trim()).filter(Boolean);
}

async function saveCourse(course) {
  const edit = editCourses.value[course.id];
  const names = parseMarks(edit.marksText);
  if (!edit.name.trim() || !names.length) return;
  if (
    course.marks.length > names.length &&
    !confirm(
      "Banan får färre märken — rundningar vid borttagna märken raderas i race som seglar den. Fortsätt?"
    )
  )
    return;
  try {
    await api.adminPatchCourse(editing.value.id, course.id, {
      name: edit.name.trim(),
      marks: names,
    });
    notice.value = "Banan sparad.";
    await openRegatta(editing.value.id);
  } catch (e) {
    error.value = e.message;
  }
}

async function removeCourse(course) {
  if (!confirm(`Ta bort banan ${course.name}?`)) return;
  try {
    await api.adminDeleteCourse(editing.value.id, course.id);
    await openRegatta(editing.value.id);
  } catch (e) {
    error.value = e.message;
  }
}

async function addCourse() {
  const names = parseMarks(newEditCourse.value.marksText);
  if (!newEditCourse.value.name.trim() || !names.length) return;
  try {
    await api.adminAddCourse(editing.value.id, {
      name: newEditCourse.value.name.trim(),
      marks: names,
    });
    newEditCourse.value = { name: "", marksText: "" };
    await openRegatta(editing.value.id);
  } catch (e) {
    error.value = e.message;
  }
}

async function saveRegatta() {
  error.value = "";
  try {
    const body = {
      ...editForm.value,
      lat: editForm.value.lat === "" ? null : editForm.value.lat,
      lon: editForm.value.lon === "" ? null : editForm.value.lon,
      start_date: editForm.value.start_date || null,
      end_date: editForm.value.end_date || null,
    };
    await api.patchRegatta(editing.value.id, body);
    notice.value = "Sparat.";
    await openRegatta(editing.value.id);
    await loadList();
  } catch (e) {
    error.value = e.message;
  }
}

async function removeRegatta() {
  if (!confirm(`Radera ${editing.value.name} med alla race och rundningar?`)) return;
  try {
    await api.deleteRegatta(editing.value.id);
    editing.value = null;
    await loadList();
  } catch (e) {
    error.value = e.message;
  }
}

async function resetRace(race) {
  if (
    !confirm(
      `Nollställ race ${race.number}? Alla rundningar, båtmarkeringar och hela protokollet för racet raderas. Detta kan inte ångras.`
    )
  )
    return;
  try {
    await api.adminResetRace(editing.value.id, race.number);
    notice.value = `Race ${race.number} nollställt.`;
    await openRegatta(editing.value.id);
  } catch (e) {
    error.value = e.message;
  }
}

async function importToExisting(replace) {
  if (!importUrl.value) return;
  previewLoading.value = true;
  error.value = "";
  try {
    const preview = await api.sailarenaPreview(importUrl.value);
    const result = await api.importBoats(editing.value.id, preview.boats || [], replace);
    notice.value = `Import klar: ${result.added} nya båtar (${result.total} totalt).`;
    await openRegatta(editing.value.id);
  } catch (e) {
    error.value = e.message;
  } finally {
    previewLoading.value = false;
  }
}

async function toggleBoat(boat) {
  await api.adminPatchBoat(editing.value.id, boat.id, { active: !boat.active });
  await openRegatta(editing.value.id);
}

async function deleteBoat(boat) {
  if (!confirm(`Radera ${boat.sail_number}? Eventuella rundningar försvinner.`)) return;
  try {
    await api.adminDeleteBoat(editing.value.id, boat.id);
    await openRegatta(editing.value.id);
  } catch (e) {
    error.value = e.message;
  }
}

const newBoat = ref({ sail_number: "", boat_name: "", boat_type: "", skipper: "", club: "" });

async function addBoat() {
  if (!newBoat.value.sail_number.trim()) return;
  try {
    await api.adminAddBoat(editing.value.id, newBoat.value);
    newBoat.value = { sail_number: "", boat_name: "", boat_type: "", skipper: "", club: "" };
    await openRegatta(editing.value.id);
  } catch (e) {
    error.value = e.message;
  }
}

const reportUrl = computed(() =>
  editing.value
    ? `${window.location.origin}/report/${editing.value.report_token}`
    : ""
);

async function copyReportUrl() {
  await navigator.clipboard.writeText(reportUrl.value);
  notice.value = "Rapporteringslänken kopierad till urklipp.";
}

async function regenerate() {
  if (
    !confirm(
      "Skapa ny hemlig länk? Den gamla slutar fungera direkt — kommittén behöver den nya."
    )
  )
    return;
  await api.regenerateToken(editing.value.id);
  await openRegatta(editing.value.id);
  notice.value = "Ny rapporteringslänk skapad.";
}
</script>

<template>
  <main class="page">
    <!-- login -->
    <template v-if="!loggedIn">
      <div class="card" style="max-width: 380px; margin: 3rem auto">
        <h2>Admin-inloggning</h2>
        <p class="error" v-if="error">{{ error }}</p>
        <div class="field">
          <label>Lösenord</label>
          <input type="password" v-model="password" @keyup.enter="login" />
        </div>
        <button class="primary" @click="login">Logga in</button>
      </div>
    </template>

    <!-- regatta list -->
    <template v-else-if="!editing && !creating">
      <div class="regatta-list-item">
        <h1>Admin</h1>
        <span>
          <button class="primary" @click="creating = true">Ny regatta</button>
          <button style="margin-left: 0.5rem" @click="logout">Logga ut</button>
        </span>
      </div>
      <p class="error" v-if="error">{{ error }}</p>
      <p v-if="!regattas.length" class="muted">Inga regattor ännu.</p>
      <div v-for="regatta in regattas" :key="regatta.id" class="card">
        <div class="regatta-list-item">
          <div>
            <strong>{{ regatta.name }}</strong>
            <div class="muted">
              {{ regatta.venue }} · {{ fmtDateRange(regatta.start_date, regatta.end_date) }}
            </div>
          </div>
          <button @click="openRegatta(regatta.id)">Redigera</button>
        </div>
      </div>
    </template>

    <!-- create -->
    <template v-else-if="creating">
      <h1>Ny regatta</h1>
      <p class="error" v-if="error">{{ error }}</p>
      <p class="muted" v-if="notice">{{ notice }}</p>
      <div class="card">
        <div class="field">
          <label>Sailarena-URL (evenemangssida eller deltagarlista)</label>
          <input v-model="form.sailarena_url" placeholder="https://www.sailarena.com/sv/se/club/…" />
        </div>
        <button @click="fetchSailarena" :disabled="previewLoading || !form.sailarena_url">
          {{ previewLoading ? "Hämtar …" : "Hämta från Sailarena" }}
        </button>
        <span class="muted" v-if="previewBoats.length" style="margin-left: 0.5rem">
          {{ previewBoats.length }} båtar redo att importeras
        </span>
      </div>
      <div class="card">
        <div class="grid-2">
          <div class="field"><label>Namn</label><input v-model="form.name" /></div>
          <div class="field"><label>Plats</label><input v-model="form.venue" /></div>
          <div class="field"><label>Arrangör</label><input v-model="form.organizer" /></div>
          <div class="field"><label>Antal race</label><input type="number" min="1" max="50" v-model.number="form.race_count" /></div>
          <div class="field"><label>Startdatum</label><input type="date" v-model="form.start_date" /></div>
          <div class="field"><label>Slutdatum</label><input type="date" v-model="form.end_date" /></div>
          <div class="field"><label>Latitud</label><input type="number" step="any" v-model.number="form.lat" /></div>
          <div class="field"><label>Longitud</label><input type="number" step="any" v-model.number="form.lon" /></div>
        </div>
        <div class="field">
          <label>Första banans namn (fler banor läggs till efter att regattan skapats)</label>
          <input v-model="form.course_name" />
        </div>
        <div class="field">
          <label>Märken — ett per rad, i rundningsordning</label>
          <textarea v-model="form.marks" rows="5"></textarea>
        </div>
        <button class="primary" @click="createRegatta" :disabled="!form.name.trim()">Skapa regatta</button>
        <button style="margin-left: 0.5rem" @click="creating = false; error = ''">Avbryt</button>
      </div>
    </template>

    <!-- edit -->
    <template v-else>
      <div class="regatta-list-item">
        <h1 style="font-size: 1.3rem">{{ editing.name }}</h1>
        <button @click="editing = null; notice = ''; loadList()">← Alla regattor</button>
      </div>
      <p class="error" v-if="error">{{ error }}</p>
      <p class="muted" v-if="notice">{{ notice }}</p>

      <div class="card">
        <h3>Rapporteringslänk till kommittén</h3>
        <p class="muted">
          Den som har länken kan rapportera utan inloggning — dela den bara med
          tävlingskommittén.
        </p>
        <p><a :href="reportUrl">{{ reportUrl }}</a></p>
        <button @click="copyReportUrl">Kopiera länk</button>
        <button class="danger" style="margin-left: 0.5rem" @click="regenerate">Skapa ny länk</button>
      </div>

      <div class="card">
        <h3>Uppgifter</h3>
        <div class="grid-2">
          <div class="field"><label>Namn</label><input v-model="editForm.name" /></div>
          <div class="field"><label>Plats</label><input v-model="editForm.venue" /></div>
          <div class="field"><label>Arrangör</label><input v-model="editForm.organizer" /></div>
          <div class="field"><label>Antal race</label><input type="number" min="1" max="50" v-model.number="editForm.race_count" /></div>
          <div class="field"><label>Startdatum</label><input type="date" v-model="editForm.start_date" /></div>
          <div class="field"><label>Slutdatum</label><input type="date" v-model="editForm.end_date" /></div>
          <div class="field"><label>Latitud</label><input type="number" step="any" v-model.number="editForm.lat" /></div>
          <div class="field"><label>Longitud</label><input type="number" step="any" v-model.number="editForm.lon" /></div>
        </div>
        <button class="primary" @click="saveRegatta">Spara</button>
        <button class="danger" style="margin-left: 0.5rem" @click="removeRegatta">Radera regatta</button>
      </div>

      <div class="card">
        <h3>Banor ({{ editing.courses.length }})</h3>
        <p class="muted">
          Kommittén väljer bana per race i rapporteringsvyn. Ett märke per rad,
          i rundningsordning. Att ta bort märken raderar rundningar vid dem.
        </p>
        <div v-for="course in editing.courses" :key="course.id" class="card" style="margin-bottom: 0.75rem">
          <div class="grid-2">
            <div class="field">
              <label>Namn</label>
              <input v-if="editCourses[course.id]" v-model="editCourses[course.id].name" />
            </div>
            <div class="field">
              <label>Märken</label>
              <textarea v-if="editCourses[course.id]" v-model="editCourses[course.id].marksText" rows="4"></textarea>
            </div>
          </div>
          <button class="primary" @click="saveCourse(course)">Spara bana</button>
          <button class="danger" style="margin-left: 0.5rem" @click="removeCourse(course)">Ta bort</button>
        </div>
        <h4>Ny bana</h4>
        <div class="grid-2">
          <div class="field">
            <label>Namn</label>
            <input v-model="newEditCourse.name" placeholder="T.ex. Kryss-läns 2 varv" />
          </div>
          <div class="field">
            <label>Märken</label>
            <textarea v-model="newEditCourse.marksText" rows="4" placeholder="Start&#10;Kryssmärke&#10;Mål"></textarea>
          </div>
        </div>
        <button class="primary" @click="addCourse" :disabled="!newEditCourse.name.trim() || !newEditCourse.marksText.trim()">
          Lägg till bana
        </button>
      </div>

      <div class="card">
        <h3>Race ({{ editing.races.length }})</h3>
        <p class="muted">
          Nollställning raderar racets rundningar, båtmarkeringar och hela
          protokollet och sätter racet till Kommande igen. Kan inte ångras —
          kommittén kan inte göra detta via rapporteringslänken.
        </p>
        <table>
          <thead>
            <tr><th>Race</th><th>Status</th><th>Rundningar</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="race in editing.races" :key="race.id">
              <td><strong>Race {{ race.number }}</strong></td>
              <td>{{ raceStatusLabel[race.status] }}</td>
              <td>{{ race.rounding_count }}</td>
              <td style="text-align: right">
                <button class="danger" @click="resetRace(race)">Nollställ</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card">
        <h3>Deltagare ({{ editing.boats.length }})</h3>
        <div class="field">
          <label>Hämta/uppdatera från Sailarena</label>
          <input v-model="importUrl" placeholder="https://www.sailarena.com/…" />
        </div>
        <button @click="importToExisting(false)" :disabled="previewLoading || !importUrl">
          Importera nya
        </button>
        <button style="margin-left: 0.5rem" @click="importToExisting(true)" :disabled="previewLoading || !importUrl">
          Ersätt listan
        </button>
        <table style="margin-top: 0.75rem">
          <thead>
            <tr><th>Segelnr</th><th>Båt</th><th>Typ</th><th>Rorsman</th><th>Klubb</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="boat in editing.boats" :key="boat.id">
              <td><strong>{{ boat.sail_number }}</strong></td>
              <td>{{ boat.boat_name }}</td>
              <td>{{ boat.boat_type }}</td>
              <td>{{ boat.skipper }}</td>
              <td>{{ boat.club }}</td>
              <td class="muted">{{ boat.active ? "Deltar" : "Utgått" }}</td>
              <td style="text-align: right; white-space: nowrap">
                <button @click="toggleBoat(boat)">{{ boat.active ? "Ta bort" : "Ta med" }}</button>
                <button class="danger" style="margin-left: 0.4rem" @click="deleteBoat(boat)">Radera</button>
              </td>
            </tr>
          </tbody>
        </table>
        <h4 style="margin-top: 1rem">Lägg till båt</h4>
        <div class="grid-2">
          <div class="field"><label>Segelnummer</label><input v-model="newBoat.sail_number" /></div>
          <div class="field"><label>Båtnamn</label><input v-model="newBoat.boat_name" /></div>
          <div class="field"><label>Båttyp</label><input v-model="newBoat.boat_type" /></div>
          <div class="field"><label>Rorsman</label><input v-model="newBoat.skipper" /></div>
        </div>
        <button class="primary" @click="addBoat" :disabled="!newBoat.sail_number.trim()">Lägg till</button>
      </div>
    </template>
  </main>
</template>
